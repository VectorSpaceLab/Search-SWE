#!/usr/bin/env python3
"""Private verifier for Task-1-1 Bright biology retrieval."""

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


TASK_ID = "task-1-1"
TASK_DATA = Path("/task/data")
PRIVATE_DATA = Path("/tests/data")
SUBMISSION_DIR = Path("/app")
WORK_DIR = Path("/tmp/task-1-1-eval")
INPUT_DIR = WORK_DIR / "input"
INDEX_DIR = WORK_DIR / "index"
OUTPUT_DIR = WORK_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "results.jsonl"
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/task-1-1-eval")
)
REPORT_PATH = RESULTS_DIR / "evaluation.json"
CORPUS_PATH = TASK_DATA / "corpus.jsonl"
TOP_K = 3
BUILD_TIMEOUT_SECONDS = 1800.0
RUN_TIMEOUT_SECONDS = 900.0
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
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
        doc_id = require_text(row.get("id"), location=f"corpus line {line_number} id")
        require_text(
            row.get("content"), location=f"corpus document {doc_id!r} content"
        )
        if doc_id in corpus_ids:
            raise VerificationError(f"duplicate corpus document ID {doc_id!r}")
        corpus_order[doc_id] = len(corpus_order)
        corpus_ids.add(doc_id)
    return corpus_ids, corpus_order


def load_private_data(
    corpus_ids: set[str],
) -> tuple[list[dict[str, str]], dict[str, set[str]]]:
    queries: list[dict[str, str]] = []
    query_ids: set[str] = set()
    for line_number, row in enumerate(
        read_jsonl(PRIVATE_DATA / "queries.jsonl"), start=1
    ):
        query_id = require_text(
            row.get("query_id"), location=f"private query line {line_number} query_id"
        )
        query_text = require_text(
            row.get("text"), location=f"private query {query_id!r} text"
        )
        if query_id in query_ids:
            raise VerificationError(f"duplicate private query ID {query_id!r}")
        query_ids.add(query_id)
        queries.append({"query_id": query_id, "text": query_text})
    if len(queries) != 3:
        raise VerificationError(f"expected exactly 3 hidden queries, got {len(queries)}")

    ground_truth: dict[str, set[str]] = {}
    for line_number, row in enumerate(
        read_jsonl(PRIVATE_DATA / "ground_truth.jsonl"), start=1
    ):
        query_id = require_text(
            row.get("query_id"), location=f"ground truth line {line_number} query_id"
        )
        relevant = row.get("relevant_doc_ids")
        if query_id not in query_ids or query_id in ground_truth:
            raise VerificationError(
                f"unknown or duplicate ground-truth query ID {query_id!r}"
            )
        if (
            not isinstance(relevant, list)
            or not relevant
            or not all(isinstance(doc_id, str) and doc_id for doc_id in relevant)
        ):
            raise VerificationError(
                f"invalid relevant_doc_ids for private query {query_id!r}"
            )
        relevant_ids = set(relevant)
        if len(relevant_ids) != len(relevant):
            raise VerificationError(
                f"duplicate relevant document for private query {query_id!r}"
            )
        unknown = sorted(relevant_ids - corpus_ids)
        if unknown:
            raise VerificationError(
                f"private query {query_id!r} references unknown document {unknown[0]!r}"
            )
        ground_truth[query_id] = relevant_ids
    if set(ground_truth) != query_ids:
        raise VerificationError("private queries and ground truth do not align")
    return queries, ground_truth


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
            returncode = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_group(process)
            stop_submission_processes()
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


def stage_queries(queries: list[dict[str, str]]) -> Path:
    path = INPUT_DIR / "queries.jsonl"
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
) -> list[dict[str, Any]]:
    if OUTPUT_PATH.is_symlink() or not OUTPUT_PATH.is_file():
        raise VerificationError("run.sh did not create a regular results.jsonl file")
    if OUTPUT_PATH.stat().st_size > MAX_OUTPUT_BYTES:
        raise VerificationError("results.jsonl exceeds the output size limit")
    rows = read_jsonl(OUTPUT_PATH)
    if len(rows) != len(queries):
        raise VerificationError(
            f"expected {len(queries)} output rows, got {len(rows)}"
        )
    expected_ids = [row["query_id"] for row in queries]
    seen: set[str] = set()
    normalized: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(rows, start=1):
        query_id = str(row.get("query_id", ""))
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
            doc_id = str(item["doc_id"])
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


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "task_id": TASK_ID,
        "valid": False,
        "reward": 0.0,
        "errors": [],
    }
    try:
        if EXECUTION_ERROR:
            raise VerificationError(EXECUTION_ERROR)
        recreate_workdirs()
        corpus_ids, corpus_order = load_corpus()
        queries, ground_truth = load_private_data(corpus_ids)
        query_path = stage_queries(queries)
        check_submission_boundary()

        build_metrics = run_timed(
            [
                str(SUBMISSION_DIR / "build.sh"),
                "--corpus",
                str(CORPUS_PATH),
                "--index-dir",
                str(INDEX_DIR),
            ],
            timeout=BUILD_TIMEOUT_SECONDS,
            stdout_path=RESULTS_DIR / "build.stdout.log",
            stderr_path=RESULTS_DIR / "build.stderr.log",
        )
        report["build"] = build_metrics
        require_success(build_metrics, "build.sh")

        run_metrics = run_timed(
            [
                str(SUBMISSION_DIR / "run.sh"),
                "--index-dir",
                str(INDEX_DIR),
                "--queries",
                str(query_path),
                "--output",
                str(OUTPUT_PATH),
                "--top-k",
                str(TOP_K),
            ],
            timeout=RUN_TIMEOUT_SECONDS,
            stdout_path=RESULTS_DIR / "run.stdout.log",
            stderr_path=RESULTS_DIR / "run.stderr.log",
        )
        report["run"] = run_metrics
        require_success(run_metrics, "run.sh")
        stop_submission_processes()

        results = validate_output(queries, corpus_ids, corpus_order)
        per_query: list[dict[str, Any]] = []
        hit_count = 0
        for row in results:
            query_id = row["query_id"]
            first_hit_rank = next(
                (
                    rank
                    for rank, doc_id in enumerate(row["results"], start=1)
                    if doc_id in ground_truth[query_id]
                ),
                None,
            )
            hit = first_hit_rank is not None
            hit_count += int(hit)
            per_query.append(
                {
                    "query_id": query_id,
                    "hit_at_3": hit,
                    "first_relevant_rank": first_hit_rank,
                    "returned_doc_ids": row["results"],
                }
            )

        raw_accuracy = hit_count / len(queries)
        all_cases_passed = hit_count == len(queries)
        gated_accuracy = 1.0 if all_cases_passed else 0.0
        report.update(
            {
                "valid": True,
                "query_count": len(queries),
                "passed_queries": hit_count,
                "raw_accuracy_at_3": raw_accuracy,
                "all_cases_passed": all_cases_passed,
                "primary_metric": {
                    "name": "Accuracy@3",
                    "value": gated_accuracy,
                    "raw_value": raw_accuracy,
                    "all_queries_required": True,
                },
                "reward": gated_accuracy,
                "queries": per_query,
            }
        )
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        stop_submission_processes()

    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
