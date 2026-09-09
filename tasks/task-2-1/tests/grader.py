#!/usr/bin/env python3
"""Hidden verifier for Task-2-1 long-document reranking."""

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


CORPUS_PATH = Path("/task/data/corpus.jsonl")
QUERIES_PATH = Path("/tests/data/queries.jsonl")
GROUND_TRUTH_PATH = Path("/tests/data/ground_truth.jsonl")
WORK_DIR = Path("/tmp/search-swe-task2-1-verifier")
INDEX_DIR = WORK_DIR / "index"
INPUT_QUERIES_PATH = WORK_DIR / "hidden-queries.jsonl"
OUTPUT_PATH = WORK_DIR / "results.jsonl"
REPEAT_OUTPUT_PATH = WORK_DIR / "results-repeat.jsonl"
REPORT_PATH = Path("/logs/verifier/report.json")
REWARD_PATH = Path("/logs/verifier/reward.txt")
BUILD_TIMEOUT = 1800.0
RUN_TIMEOUT = 3600.0
MAX_CANDIDATES = 100
METRIC_K = 5
SUBMISSION_PREFIX = ["/usr/sbin/runuser", "-u", "submission", "--"]


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def load_corpus_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for line_number, row in enumerate(read_jsonl(path), 1):
        raw_id = row.get("_id", row.get("doc_id"))
        if raw_id is None or not str(raw_id):
            raise ValueError(f"{path}:{line_number}: missing document ID")
        doc_id = str(raw_id)
        if doc_id in ids:
            raise ValueError(f"{path}:{line_number}: duplicate document ID {doc_id}")
        text = row.get("text", "")
        title = row.get("title", "")
        if not isinstance(text, str) or not isinstance(title, str):
            raise ValueError(f"{path}:{line_number}: title/text must be strings")
        if not (text.strip() or title.strip()):
            raise ValueError(f"{path}:{line_number}: empty document")
        ids.add(doc_id)
    if not ids:
        raise ValueError("corpus is empty")
    return ids


def load_queries(path: Path, corpus_ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows = read_jsonl(path)
    query_ids: list[str] = []
    seen_query_ids: set[str] = set()
    for line_number, row in enumerate(rows, 1):
        raw_query_id = row.get("_id", row.get("query_id"))
        if raw_query_id is None or not str(raw_query_id):
            raise ValueError(f"{path}:{line_number}: missing query ID")
        query_id = str(raw_query_id)
        if query_id in seen_query_ids:
            raise ValueError(f"{path}:{line_number}: duplicate query ID {query_id}")
        seen_query_ids.add(query_id)
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{path}:{line_number}: query text is empty")
        candidates = row.get("bm25_top_100")
        if not isinstance(candidates, list) or len(candidates) != MAX_CANDIDATES:
            raise ValueError(
                f"{path}:{line_number}: expected exactly {MAX_CANDIDATES} candidates"
            )
        seen_doc_ids: set[str] = set()
        for position, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                raise ValueError(f"{path}:{line_number}: candidate {position} is not an object")
            doc_id = str(candidate.get("doc_id", ""))
            if not doc_id or doc_id not in corpus_ids:
                raise ValueError(f"{path}:{line_number}: invalid candidate doc_id {doc_id!r}")
            if doc_id in seen_doc_ids:
                raise ValueError(f"{path}:{line_number}: duplicate candidate doc_id {doc_id}")
            seen_doc_ids.add(doc_id)
            if candidate.get("bm25_rank") != position:
                raise ValueError(
                    f"{path}:{line_number}: candidate {position} has invalid bm25_rank"
                )
            if not finite_number(candidate.get("bm25_score")):
                raise ValueError(f"{path}:{line_number}: candidate {position} has invalid bm25_score")
        query_ids.append(query_id)
    if not rows:
        raise ValueError(f"{path}: no queries")
    return rows, query_ids


def load_ground_truth(path: Path, query_ids: list[str]) -> dict[str, str]:
    expected = set(query_ids)
    result: dict[str, str] = {}
    for line_number, row in enumerate(read_jsonl(path), 1):
        query_id = str(row.get("query_id", ""))
        relevant = row.get("relevant_doc_ids")
        if query_id not in expected or query_id in result:
            raise ValueError(f"{path}:{line_number}: invalid or duplicate query ID")
        if not isinstance(relevant, list) or len(relevant) != 1 or not str(relevant[0]):
            raise ValueError(f"{path}:{line_number}: expected exactly one relevant document")
        result[query_id] = str(relevant[0])
    if set(result) != expected:
        raise ValueError(f"{path}: ground truth does not cover exactly the query set")
    return result


def run_command(command: list[str], timeout: float) -> tuple[int, str, str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(command)}") from error
    return process.returncode, stdout, stderr


def run_submission(command: list[str], timeout: float) -> tuple[int, str, str]:
    return run_command([*SUBMISSION_PREFIX, *command], timeout)


def stop_starter_service() -> None:
    pid_path = INDEX_DIR / "service.pid"
    try:
        raw_pid = pid_path.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (OSError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def load_results(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def validate_results(
    rows: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    query_ids: list[str],
    top_k: int,
) -> list[bool]:
    if len(rows) != len(queries):
        raise ValueError(f"expected {len(queries)} output rows, got {len(rows)}")
    hits: list[bool] = []
    for query, query_id, row in zip(queries, query_ids, rows):
        if str(row.get("query_id", "")) != query_id:
            raise ValueError(f"output query order/ID mismatch for {query_id}")
        results = row.get("results")
        if not isinstance(results, list) or len(results) != top_k:
            raise ValueError(f"{query_id}: expected exactly {top_k} results")
        expected_doc_ids = {
            str(candidate["doc_id"]) for candidate in query["bm25_top_100"]
        }
        candidate_order = {
            str(candidate["doc_id"]): position
            for position, candidate in enumerate(query["bm25_top_100"])
        }
        seen: set[str] = set()
        previous_score: float | None = None
        previous_candidate_position: int | None = None
        ranked_ids: list[str] = []
        for position, result in enumerate(results, 1):
            if not isinstance(result, dict):
                raise ValueError(f"{query_id}: result {position} is not an object")
            doc_id = str(result.get("doc_id", ""))
            if not doc_id or doc_id in seen:
                raise ValueError(f"{query_id}: empty or duplicate result doc_id")
            if doc_id not in expected_doc_ids:
                raise ValueError(f"{query_id}: result contains a document outside the candidate pool")
            score = result.get("score")
            if not finite_number(score):
                raise ValueError(f"{query_id}: result {position} has a non-finite score")
            score = float(score)
            if previous_score is not None and score > previous_score:
                raise ValueError(f"{query_id}: scores are not non-increasing")
            if (
                previous_score is not None
                and score == previous_score
                and previous_candidate_position is not None
                and candidate_order[doc_id] < previous_candidate_position
            ):
                raise ValueError(
                    f"{query_id}: equal-score results are not in candidate order"
                )
            seen.add(doc_id)
            ranked_ids.append(doc_id)
            previous_score = score
            previous_candidate_position = candidate_order[doc_id]
        gold = query.get("_gold_doc_id")
        hits.append(str(gold) in set(ranked_ids[:METRIC_K]))
    return hits


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REWARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    reward = float(report.get("reward", 0.0)) if report.get("valid") else 0.0
    REWARD_PATH.write_text(f"{max(0.0, min(1.0, reward)):.10f}\n", encoding="utf-8")


def main() -> int:
    started = time.monotonic()
    report: dict[str, Any] = {
        "task_id": "task-2-1",
        "valid": False,
        "reward": 0.0,
        "primary_metric": "Accuracy@5",
        "query_count": 0,
        "errors": [],
    }
    try:
        corpus_ids = load_corpus_ids(CORPUS_PATH)
        queries, query_ids = load_queries(QUERIES_PATH, corpus_ids)
        ground_truth = load_ground_truth(GROUND_TRUTH_PATH, query_ids)
        if not all(doc_id in corpus_ids for doc_id in ground_truth.values()):
            raise ValueError("ground truth contains a document absent from the corpus")
        for query, query_id in zip(queries, query_ids):
            query["_gold_doc_id"] = ground_truth[query_id]

        for path in (Path("/app/build.sh"), Path("/app/run.sh")):
            if not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError(f"missing executable submission entry point: {path}")
        forbidden_extensions = {".safetensors", ".pt", ".pth", ".bin", ".onnx"}
        submitted_weights = [
            str(path) for path in Path("/app").rglob("*")
            if path.is_file() and path.suffix in forbidden_extensions
        ]
        if submitted_weights:
            raise ValueError(f"submission added model/checkpoint files under /app: {submitted_weights[:5]}")

        shutil.rmtree(WORK_DIR, ignore_errors=True)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        shutil.chown(WORK_DIR, user="submission", group="submission")
        shutil.copyfile(QUERIES_PATH, INPUT_QUERIES_PATH)
        shutil.chown(INPUT_QUERIES_PATH, user="submission", group="submission")
        INPUT_QUERIES_PATH.chmod(0o444)
        returncode, stdout, stderr = run_submission(
            [
                "/app/build.sh",
                "--corpus",
                str(CORPUS_PATH),
                "--index-dir",
                str(INDEX_DIR),
            ],
            BUILD_TIMEOUT,
        )
        if returncode != 0:
            raise RuntimeError(f"build.sh failed with status {returncode}: {stderr[-4000:]}")
        if not any(INDEX_DIR.rglob("*")):
            raise RuntimeError("build.sh produced an empty index")

        for output_path in (OUTPUT_PATH, REPEAT_OUTPUT_PATH):
            output_path.unlink(missing_ok=True)
            returncode, stdout, stderr = run_submission(
                [
                    "/app/run.sh",
                    "--index-dir",
                    str(INDEX_DIR),
                    "--queries",
                    str(INPUT_QUERIES_PATH),
                    "--output",
                    str(output_path),
                    "--top-k",
                    str(METRIC_K),
                ],
                RUN_TIMEOUT,
            )
            if returncode != 0:
                raise RuntimeError(f"run.sh failed with status {returncode}: {stderr[-4000:]}")
            if not output_path.is_file() or not output_path.stat().st_size:
                raise RuntimeError(f"run.sh did not produce {output_path}")

        if OUTPUT_PATH.read_bytes() != REPEAT_OUTPUT_PATH.read_bytes():
            raise RuntimeError("repeated run.sh output is not byte-for-byte deterministic")
        result_rows = load_results(OUTPUT_PATH)
        hits = validate_results(result_rows, queries, query_ids, METRIC_K)
        hit_count = sum(hits)
        reward = hit_count / len(query_ids)
        report.update(
            {
                "valid": True,
                "reward": reward,
                "query_count": len(query_ids),
                "hit_at_5_count": hit_count,
                "miss_at_5_count": len(query_ids) - hit_count,
                "elapsed_seconds": time.monotonic() - started,
            }
        )
        write_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        report["errors"] = [str(error)]
        report["elapsed_seconds"] = time.monotonic() - started
        write_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        stop_starter_service()


if __name__ == "__main__":
    raise SystemExit(main())
