#!/usr/bin/env python3
"""Private verifier for complete-set biomedical graph retrieval."""

from __future__ import annotations

import json
import sqlite3
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


TASK_ID = "biomedical-graph-retrieval"
TASK_DATA = Path("/task/data")
PRIVATE_DATA = Path("/tests/data")
SUBMISSION_DIR = Path("/app")
WORK_DIR = Path("/tmp/biomedical-graph-retrieval-eval")
INPUT_DIR = WORK_DIR / "input"
INDEX_DIR = WORK_DIR / "index"
OUTPUT_DIR = WORK_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "results.jsonl"
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/biomedical-graph-retrieval-eval")
)
REPORT_PATH = RESULTS_DIR / "evaluation.json"
CORPUS_PATH = TASK_DATA / "corpus.sqlite"
HIDDEN_QUERY_COUNT = 20
BUILD_TIMEOUT_SECONDS = 1800.0
RUN_TIMEOUT_SECONDS = 30.0
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


def load_corpus() -> set[int]:
    with sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True) as connection:
        ids = {row[0] for row in connection.execute("SELECT id FROM nodes")}
    if not ids or any(type(i) is not int for i in ids):
        raise VerificationError("invalid graph node IDs")
    return ids


def require_ids(value: Any, corpus_ids: set[int], *, location: str) -> set[int]:
    if not isinstance(value, list) or any(type(i) is not int for i in value):
        raise VerificationError(f"{location} must be a list of JSON integers")
    ids = set(value)
    if len(ids) != len(value):
        raise VerificationError(f"{location} contains duplicate node IDs")
    if not ids <= corpus_ids:
        raise VerificationError(f"{location} contains unknown node IDs")
    return ids


def load_private_data(corpus_ids: set[int]) -> tuple[list[dict[str, str]], dict[str, set[int]]]:
    queries = []
    query_ids = set()
    for row in read_jsonl(PRIVATE_DATA / "queries.jsonl"):
        query_id = require_text(row.get("query_id"), location="private query_id")
        text = require_text(row.get("query"), location=f"private query {query_id!r}")
        if query_id in query_ids:
            raise VerificationError(f"duplicate private query ID {query_id!r}")
        query_ids.add(query_id)
        queries.append({"query_id": query_id, "query": text})
    if len(queries) != HIDDEN_QUERY_COUNT:
        raise VerificationError(f"expected {HIDDEN_QUERY_COUNT} hidden queries, got {len(queries)}")
    gold = {}
    for row in read_jsonl(PRIVATE_DATA / "ground_truth.jsonl"):
        query_id = require_text(row.get("query_id"), location="ground truth query_id")
        if query_id not in query_ids or query_id in gold:
            raise VerificationError(f"unknown or duplicate gold query ID {query_id!r}")
        gold[query_id] = require_ids(row.get("answer_ids"), corpus_ids, location=f"gold {query_id!r}")
    if set(gold) != query_ids:
        raise VerificationError("private queries and ground truth do not align")
    return queries, gold


def submission_command(command: list[str]) -> list[str]:
    environment = [
        f"HOME={INDEX_DIR}",
        "USER=submission",
        "LOGNAME=submission",
        "JAVA_HOME=/opt/java/openjdk",
        "PATH=/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
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
            returncode = process.wait(timeout=max(0.0, timeout - (time.monotonic() - started)))
            timed_out = time.monotonic() - started > timeout
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_group(process)
            # Preserve build-started services for later queries. Global cleanup
            # still runs when the whole evaluation finishes or the build fails.
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
            "test -r /task/data/corpus.sqlite",
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
    corpus_ids: set[int],
    *,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows = read_jsonl(OUTPUT_PATH if output_path is None else output_path)
    expected = [q["query_id"] for q in queries]
    if len(rows) != len(expected):
        raise VerificationError(f"expected {len(expected)} output rows, got {len(rows)}")
    normalized = {}
    for row in rows:
        query_id = require_text(row.get("query_id"), location="output query_id")
        if query_id not in expected or query_id in normalized:
            raise VerificationError(f"invalid or duplicate output query_id {query_id!r}")
        ids = require_ids(row.get("answer_ids"), corpus_ids, location=f"output {query_id!r}")
        normalized[query_id] = {"query_id": query_id, "answer_ids": sorted(ids)}
    return [normalized[i] for i in expected]


def score_answers(results: list[dict[str, Any]], gold: dict[str, set[int]]) -> list[dict[str, Any]]:
    return [{"query_id": row["query_id"],
             "exact_match": not row.get("timed_out", False) and set(row["answer_ids"]) == gold[row["query_id"]],
             "returned_node_ids": row["answer_ids"],
             "timed_out": row.get("timed_out", False)} for row in results]


def run_queries(
    queries: list[dict[str, str]],
    corpus_ids: set[int],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reveal and time one request at a time; unused time cannot be pooled."""
    metrics.update(
        returncode=None,
        elapsed_seconds=0.0,
        timed_out=False,
        per_query_timeout_seconds=RUN_TIMEOUT_SECONDS,
        queries=[],
    )
    results: list[dict[str, Any]] = []
    for position, query in enumerate(queries, start=1):
        filename = f"query-{position:03d}.jsonl"
        query_path = stage_queries([query], filename=filename)
        # A late service response from an earlier query has its own path.
        output_path = OUTPUT_DIR / filename
        output_path.unlink(missing_ok=True)
        query_metrics = run_timed(
            [
                str(SUBMISSION_DIR / "run.sh"),
                "--index-dir", str(INDEX_DIR),
                "--queries", str(query_path),
                "--output", str(output_path),
            ],
            timeout=RUN_TIMEOUT_SECONDS,
            stdout_path=RESULTS_DIR / f"query-{position:03d}.stdout.log",
            stderr_path=RESULTS_DIR / f"query-{position:03d}.stderr.log",
        )
        metrics["queries"].append({"query_id": query["query_id"], **query_metrics})
        if metrics["returncode"] in (None, 0):
            metrics["returncode"] = query_metrics["returncode"]
        metrics["elapsed_seconds"] += query_metrics["elapsed_seconds"]
        metrics["timed_out"] = metrics["timed_out"] or query_metrics["timed_out"]
        if query_metrics["timed_out"]:
            # Ignore even a well-formed output if run.sh missed its deadline.
            results.append({"query_id": query["query_id"], "answer_ids": [], "timed_out": True})
            continue
        require_success(query_metrics, f"run.sh query {query['query_id']!r}")
        results.extend(validate_output([query], corpus_ids, output_path=output_path))
    return results


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
        corpus_ids = load_corpus()
        queries, ground_truth = load_private_data(corpus_ids)
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

        report["run"] = {}
        results = run_queries(queries, corpus_ids, report["run"])
        stop_submission_processes()
        per_query = score_answers(results, ground_truth)
        hit_count = sum(row["exact_match"] for row in per_query)

        raw_accuracy = hit_count / len(queries)
        all_cases_passed = hit_count == len(queries)
        report.update(
            {
                "valid": True,
                "query_count": len(queries),
                "passed_queries": hit_count,
                "timed_out_queries": sum(row["timed_out"] for row in per_query),
                "exact_set_accuracy": raw_accuracy,
                "all_cases_passed": all_cases_passed,
                "primary_metric": {
                    "name": "ExactSetAccuracy",
                    "value": raw_accuracy,
                    "raw_value": raw_accuracy,
                    "all_queries_required": False,
                },
                "reward": raw_accuracy,
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
