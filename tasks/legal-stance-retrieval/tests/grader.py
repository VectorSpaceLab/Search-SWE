#!/usr/bin/env python3
"""Private verifier for stance retrieval using five independent timed batches."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil


TASK_ID = "legal-stance-retrieval"
TASK_DATA = Path("/task/data")
PRIVATE_DATA = Path("/tests/data")
SUBMISSION_DIR = Path("/app")
WORK_DIR = Path("/tmp/legal-stance-retrieval-eval")
INPUT_DIR = WORK_DIR / "input"
INDEX_DIR = WORK_DIR / "index"
OUTPUT_DIR = WORK_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "results.jsonl"
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/legal-stance-retrieval-eval")
)
REPORT_PATH = RESULTS_DIR / "evaluation.json"
CORPUS_PATH = TASK_DATA / "corpus.jsonl"
TOP_K = 10
HIDDEN_QUERY_COUNT = 311
BUILD_TIMEOUT_SECONDS = 3600.0
RUN_TIMEOUT_SECONDS = 20.0
QUERY_REPEATS = 5
BASELINE_B = 0.5610484855098774
SUBMISSION_UID = 10001
SUBMISSION_GID = 10001
SUBMISSION_USER = "submission"
EXECUTION_ERROR = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")


class VerificationError(RuntimeError):
    """Raised when verifier inputs or submission behavior are invalid."""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        handle = path.open(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot read {path}: {error}") from error
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise VerificationError(
                    f"invalid JSON in {path}:{line_number}: {error}"
                ) from error
            if not isinstance(value, dict):
                raise VerificationError(f"{path}:{line_number} is not an object")
            rows.append(value)
    if not rows:
        raise VerificationError(f"{path} has no records")
    return rows


def require_text(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"{location} must be a non-empty string")
    return value


def load_corpus() -> tuple[set[str], dict[str, int]]:
    corpus_ids: set[str] = set()
    corpus_order: dict[str, int] = {}
    for line_number, row in enumerate(read_jsonl(CORPUS_PATH), start=1):
        doc_id = require_text(row.get("doc_id"), location=f"corpus line {line_number} id")
        require_text(
            row.get("text"), location=f"corpus document {doc_id!r} content"
        )
        if doc_id in corpus_ids:
            raise VerificationError(f"duplicate corpus document ID {doc_id!r}")
        corpus_order[doc_id] = len(corpus_order)
        corpus_ids.add(doc_id)
    return corpus_ids, corpus_order


def load_private_data(corpus_ids: set[str]) -> tuple[list[dict[str, str]], dict[str, set[str]]]:
    queries = read_jsonl(PRIVATE_DATA / "queries.jsonl")
    ids = set()
    for row in queries:
        qid = require_text(row.get("query_id"), location="query_id")
        require_text(row.get("query"), location=f"query {qid}")
        if qid in ids or row.get("stance") not in ("supported", "refuted", "all"):
            raise VerificationError(f"invalid or duplicate input {qid}")
        ids.add(qid)
    if len(queries) != HIDDEN_QUERY_COUNT:
        raise VerificationError(f"expected {HIDDEN_QUERY_COUNT} hidden queries")
    gold = {}
    for row in read_jsonl(PRIVATE_DATA / "ground_truth.jsonl"):
        qid = row.get("query_id")
        relevance = row.get("relevance")
        if qid not in ids or qid in gold or not isinstance(relevance, dict) or not relevance:
            raise VerificationError("invalid private relevance record")
        if not set(relevance) <= corpus_ids or any(type(v) is not int or v != 1 for v in relevance.values()):
            raise VerificationError("qrels must reference corpus IDs with binary positive relevance")
        gold[qid] = set(relevance)
    if set(gold) != ids:
        raise VerificationError("private queries and qrels do not align")
    return queries, gold


def submission_command(command: list[str]) -> list[str]:
    environment = [
        f"HOME={INDEX_DIR}",
        "USER=submission",
        "LOGNAME=submission",
        "PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
        "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1",
        "TOKENIZERS_PARALLELISM=false",
        "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1",
        "OMP_NUM_THREADS=16",
        f"TMPDIR={INDEX_DIR / 'tmp'}",
        f"XDG_CACHE_HOME={INDEX_DIR / 'cache'}",
    ]
    for name in (
        "OPENROUTER_API_KEY",
        "JINA_API_KEY",
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "no_proxy",
    ):
        value = os.environ.get(name)
        if value:
            environment.append(f"{name}={value}")
    return [
        "/usr/sbin/runuser",
        "-u",
        SUBMISSION_USER,
        "--",
        "/usr/bin/setpriv",
        "--no-new-privs",
        "/usr/bin/env",
        "-i",
        *environment,
        *command,
    ]


def stop_submission_processes() -> None:
    for signal_name in ("TERM", "KILL"):
        subprocess.run(
            ["/usr/bin/pkill", f"-{signal_name}", "-u", SUBMISSION_USER],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if signal_name == "TERM":
            time.sleep(0.5)
    deadline = time.monotonic() + 10
    while True:
        live = []
        for process in psutil.process_iter(["uids", "status"]):
            try:
                if process.info["uids"].real == SUBMISSION_UID and process.info["status"] != psutil.STATUS_ZOMBIE:
                    live.append(process)
                    process.kill()
            except psutil.NoSuchProcess:
                pass
        if not live:
            return
        if time.monotonic() >= deadline:
            raise VerificationError("submission processes survived cleanup")
        time.sleep(0.01)


def clear_submission_ipc() -> None:
    """Discard writable IPC state between independently rebuilt query batches."""
    for root in (Path("/dev/shm"), Path("/dev/mqueue")):
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.lstat().st_uid == SUBMISSION_UID:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
    for table, identifier, flag in (("shm", "shmid", "-m"),
                                    ("msg", "msqid", "-q"), ("sem", "semid", "-s")):
        rows = Path("/proc/sysvipc", table).read_text().splitlines()
        columns = rows[0].split()
        for line in rows[1:]:
            row = dict(zip(columns, line.split(), strict=True))
            if SUBMISSION_UID in (int(row["uid"]), int(row["cuid"])):
                subprocess.run(
                    ["/usr/bin/setpriv", f"--reuid={SUBMISSION_UID}",
                     f"--regid={SUBMISSION_GID}", "--clear-groups", "--no-new-privs",
                     "/usr/bin/ipcrm", flag, row[identifier]],
                    check=True, timeout=5, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )


def kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.2)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_timed(
    command: list[str],
    *,
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                submission_command(command),
                cwd=SUBMISSION_DIR,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except OSError as error:
            return {
                "returncode": None,
                "elapsed_seconds": time.monotonic() - started,
                "timed_out": False,
                "error": f"could not start command: {error}",
            }
        try:
            returncode = process.wait(timeout=max(0.0, timeout - (time.monotonic() - started)))
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_group(process)
            # The main verifier cleans up every submission-owned service before scoring.
            try:
                returncode = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                returncode = None
    return {
        "returncode": returncode,
        "elapsed_seconds": time.monotonic() - started,
        "timed_out": timed_out,
    }


def require_success(metrics: dict[str, Any], label: str) -> None:
    if metrics.get("timed_out"):
        raise VerificationError(f"{label} exceeded its timeout")
    if metrics.get("returncode") != 0:
        raise VerificationError(f"{label} exited with {metrics.get('returncode')}")


def recreate_workdirs() -> None:
    if WORK_DIR.is_symlink() or (WORK_DIR.exists() and not WORK_DIR.is_dir()):
        WORK_DIR.unlink()
    elif WORK_DIR.is_dir():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(mode=0o711)
    os.chown(WORK_DIR, 0, 0)
    os.chmod(WORK_DIR, 0o711)
    INPUT_DIR.mkdir(mode=0o750)
    os.chown(INPUT_DIR, 0, SUBMISSION_GID)
    INDEX_DIR.mkdir(mode=0o750)
    os.chown(INDEX_DIR, SUBMISSION_UID, SUBMISSION_GID)
    OUTPUT_DIR.mkdir(mode=0o750)
    os.chown(OUTPUT_DIR, SUBMISSION_UID, SUBMISSION_GID)
    for child_name in ("tmp", "cache"):
        child = INDEX_DIR / child_name
        child.mkdir(mode=0o700)
        os.chown(child, SUBMISSION_UID, SUBMISSION_GID)


def stage_queries(queries: list[dict[str, str]], *, filename: str = "queries.jsonl") -> Path:
    path = INPUT_DIR / filename
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in queries
        ),
        encoding="utf-8",
    )
    os.chown(path, 0, SUBMISSION_GID)
    os.chmod(path, 0o440)
    return path


def check_submission_boundary() -> None:
    checks = " && ".join(
        [
            "test -r /task/data/corpus.jsonl",
            "test -x /app/build.sh",
            "test -x /app/run.sh",
            "test -r /task/models/Qwen3-Embedding-0.6B/model.safetensors",
            "test ! -r /tests/data/queries.jsonl",
            "test ! -r /tests/data/ground_truth.jsonl",
            'test -z "${OPENAI_API_KEY+x}"',
            'test -z "${OPENAI_BASE_URL+x}"',
            'test -z "${CODEX_HOME+x}"',
            "test ! -r /logs/agent/trajectory.json",
            "test ! -w /logs/agent",
            "test ! -w /logs/verifier",
        ]
    )
    result = subprocess.run(
        submission_command(["/bin/sh", "-c", checks]),
        cwd=SUBMISSION_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError(
            "submission permission or credential boundary is not configured correctly"
        )


def validate_output(
    queries: list[dict[str, str]],
    corpus_ids: set[str],
    corpus_order: dict[str, int],
    *,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows = read_jsonl(OUTPUT_PATH if output_path is None else output_path)
    if len(rows) != len(queries):
        raise VerificationError(
            f"expected {len(queries)} output rows, got {len(rows)}"
        )
    expected_ids = [row["query_id"] for row in queries]
    seen: set[str] = set()
    normalized: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(rows, start=1):
        query_id = require_text(row.get("query_id"), location=f"output row {line_number} query_id")
        if query_id not in expected_ids or query_id in seen:
            raise VerificationError(
                f"invalid or duplicate output query_id {query_id!r} at line {line_number}"
            )
        results = row.get("results")
        if not isinstance(results, list) or len(results) != TOP_K:
            raise VerificationError(
                f"query {query_id!r} must contain exactly {TOP_K} results"
            )
        previous_score: float | None = None
        result_ids: list[str] = []
        result_scores: list[float] = []
        for position, item in enumerate(results, start=1):
            if not isinstance(item, dict) or "doc_id" not in item or "score" not in item:
                raise VerificationError(
                    f"query {query_id!r}, result {position} is malformed"
                )
            doc_id = require_text(item["doc_id"], location=f"output row {line_number} doc_id")
            raw_score = item["score"]
            if doc_id not in corpus_ids:
                raise VerificationError(
                    f"query {query_id!r} contains unknown document {doc_id!r}"
                )
            if doc_id in result_ids:
                raise VerificationError(
                    f"query {query_id!r} contains duplicate document {doc_id!r}"
                )
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise VerificationError(
                    f"query {query_id!r}, result {position} has a non-numeric score"
                )
            score = float(raw_score)
            if not math.isfinite(score):
                raise VerificationError(
                    f"query {query_id!r}, result {position} has a non-finite score"
                )
            if previous_score is not None and score > previous_score:
                raise VerificationError(
                    f"query {query_id!r} results are not score-descending"
                )
            previous_score = score
            result_ids.append(doc_id)
            result_scores.append(score)
        seen.add(query_id)
        normalized[query_id] = {
            "query_id": query_id,
            "results": result_ids,
            "scores": result_scores,
            "corpus_rows": [corpus_order[doc_id] for doc_id in result_ids],
        }
    return [normalized[query_id] for query_id in expected_ids]


def ndcg_at_10(ranked: list[str], relevant: set[str]) -> float:
    if not relevant:
        raise VerificationError("empty qrels are not part of this task")
    dcg = sum(1.0 / math.log2(rank + 2) for rank, doc in enumerate(ranked[:TOP_K])
              if doc in relevant)
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(min(TOP_K, len(relevant))))
    return dcg / ideal


def normalize_score(mean: float) -> float:
    return max(0.0, min(1.0, (mean - BASELINE_B) / (1.0 - BASELINE_B)))


def score_results(results: list[dict[str, Any]], gold: dict[str, set[str]]) -> dict[str, Any]:
    per_query = [{"query_id": row["query_id"],
                  "ndcg_at_10": ndcg_at_10(row["results"], gold[row["query_id"]]),
                  "returned_doc_ids": row["results"]} for row in results]
    mean = sum(row["ndcg_at_10"] for row in per_query) / len(gold)
    reward = normalize_score(mean)
    return {"query_count": len(gold), "mean_ndcg_at_10": mean, "baseline_ndcg_at_10": BASELINE_B,
            "primary_metric": {"name": "baseline-normalized mean NDCG@10", "value": reward,
                               "raw_value": mean},
            "reward": reward, "queries": per_query}


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"task_id": TASK_ID, "valid": False, "reward": 0.0,
                              "errors": [], "query_repeats": QUERY_REPEATS, "attempts": []}
    try:
        if EXECUTION_ERROR:
            raise VerificationError(EXECUTION_ERROR)
        corpus_ids, corpus_order = load_corpus()
        queries, gold = load_private_data(corpus_ids)
        for repeat in range(1, QUERY_REPEATS + 1):
            stop_submission_processes()
            clear_submission_ipc()
            recreate_workdirs()
            check_submission_boundary()
            attempt: dict[str, Any] = {"repeat": repeat, "valid": False, "errors": []}
            report["attempts"].append(attempt)
            # Rebuild because the existing interface permits build-started services.
            # No query files, prior index, process or writable IPC survive a round.
            attempt["build"] = run_timed(
                [str(SUBMISSION_DIR / "build.sh"), "--corpus", str(CORPUS_PATH),
                 "--index-dir", str(INDEX_DIR)], timeout=BUILD_TIMEOUT_SECONDS,
                stdout_path=RESULTS_DIR / f"build-{repeat}.stdout.log",
                stderr_path=RESULTS_DIR / f"build-{repeat}.stderr.log")
            require_success(attempt["build"], "build.sh")
            if attempt["build"]["elapsed_seconds"] > BUILD_TIMEOUT_SECONDS:
                raise VerificationError("build.sh exceeded its deadline")
            # Stage the same frozen query order only after this round's build.
            query_path = stage_queries(queries)
            try:
                attempt["run"] = run_timed(
                    [str(SUBMISSION_DIR / "run.sh"), "--index-dir", str(INDEX_DIR),
                     "--queries", str(query_path), "--output", str(OUTPUT_PATH), "--top-k", str(TOP_K)],
                    timeout=RUN_TIMEOUT_SECONDS,
                    stdout_path=RESULTS_DIR / f"run-{repeat}.stdout.log",
                    stderr_path=RESULTS_DIR / f"run-{repeat}.stderr.log")
                stop_submission_processes()
                require_success(attempt["run"], "run.sh whole batch")
                if attempt["run"]["elapsed_seconds"] > RUN_TIMEOUT_SECONDS:
                    raise VerificationError("whole query batch exceeded 20 seconds")
                results = validate_output(queries, corpus_ids, corpus_order)
                attempt.update(score_results(results, gold))
                attempt["valid"] = True
            except VerificationError as error:
                attempt["errors"].append(f"{type(error).__name__}: {error}")
            finally:
                stop_submission_processes()
            write_json(REPORT_PATH, report)
        # Failed/late/invalid batches rank after all successful batches. Select
        # the median-time batch's rankings, never the highest relevance score.
        selected = sorted(report["attempts"], key=lambda item: (
            item["run"]["elapsed_seconds"] if item["valid"] else math.inf,
            item["repeat"],
        ))[QUERY_REPEATS // 2]
        report["median_repeat"] = selected["repeat"]
        report["successful_attempts"] = sum(item["valid"] for item in report["attempts"])
        if not selected["valid"]:
            raise VerificationError("fewer than three valid query batches within 20 seconds")
        report.update({key: selected[key] for key in (
            "build", "run", "query_count", "mean_ndcg_at_10", "baseline_ndcg_at_10",
            "primary_metric", "reward", "queries",
        )})
        report["valid"] = True
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        stop_submission_processes()
        clear_submission_ipc()
    write_json(REPORT_PATH, report)
    print(json.dumps({k: v for k, v in report.items() if k != "queries"}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
