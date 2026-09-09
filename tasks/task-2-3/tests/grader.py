#!/usr/bin/env python3
"""Validate starter and submission results and calculate the timed reward."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


CORPUS_PATH = Path("/task/data/corpus.jsonl")
VECTOR_PATH = Path("/task/data/doc.npy")
QUERIES_PATH = Path("/tests/data/queries.jsonl")
GROUND_TRUTH_PATH = Path("/tests/data/ground_truth.jsonl")
REPORT_PATH = Path("/logs/verifier/task-2-3-eval/evaluation.json")
EXPECTED_VECTOR_SHA256 = "54c2f4a5a83e43d8ab5569f195c7e478a0807c9018e0749a9f62158656c8cd46"
TOP_K = 1
TIME_LIMIT_FRACTION = 0.60
ACCURACY_BASELINE = 0.31
ACCURACY_RANGE = 0.69


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    if not rows:
        raise ValueError(f"{path}: empty")
    return rows


def load_reference_data() -> tuple[list[str], list[str], dict[str, str]]:
    corpus_rows = read_jsonl(CORPUS_PATH)
    corpus_ids = [
        str(row.get("id", row.get("_id", row.get("doc_id", ""))))
        for row in corpus_rows
    ]
    if any(not value for value in corpus_ids) or len(set(corpus_ids)) != len(corpus_ids):
        raise ValueError("corpus IDs are missing or duplicated")

    if sha256(VECTOR_PATH) != EXPECTED_VECTOR_SHA256:
        raise ValueError("fixed vector checksum mismatch")
    vectors = np.load(VECTOR_PATH, mmap_mode="r")
    if vectors.shape != (len(corpus_ids), 2560) or vectors.dtype != np.float32:
        raise ValueError(f"invalid fixed vectors: shape={vectors.shape}, dtype={vectors.dtype}")

    query_rows = read_jsonl(QUERIES_PATH)
    query_ids: list[str] = []
    for row in query_rows:
        query_id = str(row.get("query_id", row.get("_id", "")))
        text = row.get("text")
        if not query_id or not isinstance(text, str) or not text.strip() or query_id in query_ids:
            raise ValueError("invalid or duplicate query")
        query_ids.append(query_id)

    corpus_id_set = set(corpus_ids)
    ground_truth: dict[str, str] = {}
    for row in read_jsonl(GROUND_TRUTH_PATH):
        query_id = str(row.get("query_id", ""))
        relevant = row.get("relevant_doc_ids")
        if query_id in ground_truth or not isinstance(relevant, list) or len(relevant) != 1:
            raise ValueError(f"invalid or duplicate ground truth for {query_id!r}")
        doc_id = str(relevant[0])
        if doc_id not in corpus_id_set:
            raise ValueError(f"ground truth document is absent from corpus: {doc_id!r}")
        ground_truth[query_id] = doc_id
    if set(query_ids) != set(ground_truth):
        raise ValueError("queries and ground truth do not cover the same IDs")
    return query_ids, corpus_ids, ground_truth


def validate_results(
    path: Path,
    query_ids: list[str],
    corpus_ids: list[str],
    ground_truth: dict[str, str],
) -> tuple[float, list[int | None]]:
    rows = read_jsonl(path)
    if len(rows) != len(query_ids):
        raise ValueError(f"{path}: expected {len(query_ids)} result rows, got {len(rows)}")

    corpus_order = {doc_id: index for index, doc_id in enumerate(corpus_ids)}
    hits = 0
    ranks: list[int | None] = []
    for expected_query_id, row in zip(query_ids, rows):
        if str(row.get("query_id", "")) != expected_query_id:
            raise ValueError(f"{path}: query ID/order mismatch for {expected_query_id!r}")
        results = row.get("results")
        if not isinstance(results, list) or len(results) != TOP_K:
            raise ValueError(f"{path}: {expected_query_id!r} must contain exactly {TOP_K} result")

        seen: set[str] = set()
        previous_score: float | None = None
        previous_corpus_index: int | None = None
        ranked_ids: list[str] = []
        for position, result in enumerate(results, 1):
            if not isinstance(result, dict):
                raise ValueError(f"{path}: {expected_query_id!r} result {position} is not an object")
            doc_id = str(result.get("doc_id", ""))
            score = result.get("score")
            if not doc_id or doc_id not in corpus_order or doc_id in seen:
                raise ValueError(f"{path}: invalid or duplicate document ID for {expected_query_id!r}")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(float(score)):
                raise ValueError(f"{path}: invalid score for {expected_query_id!r}")
            score = float(score)
            corpus_index = corpus_order[doc_id]
            if previous_score is not None and score > previous_score:
                raise ValueError(f"{path}: scores are not descending for {expected_query_id!r}")
            if (
                previous_score is not None
                and score == previous_score
                and corpus_index < previous_corpus_index
            ):
                raise ValueError(f"{path}: equal-score tie is not in corpus order for {expected_query_id!r}")
            seen.add(doc_id)
            ranked_ids.append(doc_id)
            previous_score = score
            previous_corpus_index = corpus_index

        rank = next(
            (index + 1 for index, doc_id in enumerate(ranked_ids) if doc_id == ground_truth[expected_query_id]),
            None,
        )
        ranks.append(rank)
        hits += int(rank == 1)

    return hits / len(query_ids), ranks


def read_duration(path: Path) -> float:
    value = float(path.read_text(encoding="utf-8").strip())
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"invalid duration in {path}: {value!r}")
    return value


def read_starter_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def clamp_reward(accuracy: float) -> float:
    value = (accuracy - ACCURACY_BASELINE) / ACCURACY_RANGE
    return max(0.0, min(1.0, value))


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    started = time.monotonic()
    starter_output = Path(os.environ.get("SEARCH_SWE_STARTER_OUTPUT", "/logs/verifier/task-2-3-eval/starter-results.jsonl"))
    candidate_output = Path(os.environ.get("SEARCH_SWE_CANDIDATE_OUTPUT", "/logs/verifier/task-2-3-eval/results.jsonl"))
    starter_report_path = Path(os.environ.get("SEARCH_SWE_STARTER_REPORT", "/logs/verifier/task-2-3-eval/starter-report.json"))
    starter_time_path = Path(os.environ.get("SEARCH_SWE_STARTER_TIME_FILE", "/logs/verifier/task-2-3-eval/starter-time.txt"))
    candidate_time_path = Path(os.environ.get("SEARCH_SWE_CANDIDATE_TIME_FILE", "/logs/verifier/task-2-3-eval/candidate-time.txt"))
    execution_error = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")

    report: dict[str, Any] = {
        "task_id": "task-2-3",
        "valid": False,
        "reward": 0.0,
        "primary_metric": {"name": "Accuracy@1", "value": None},
        "query_count": 0,
        "starter_accuracy_at_1": None,
        "candidate_accuracy_at_1": None,
        "starter_elapsed_seconds": None,
        "candidate_elapsed_seconds": None,
        "time_limit_seconds": None,
        "time_passed": False,
        "errors": [],
    }

    try:
        query_ids, corpus_ids, ground_truth = load_reference_data()
        report["query_count"] = len(query_ids)
        if execution_error:
            raise ValueError(execution_error)
        run_path = Path("/app/submission/run.sh")
        if not run_path.is_file() or not os.access(run_path, os.X_OK):
            raise ValueError(
                "missing executable submission entry point: "
                "/app/submission/run.sh"
            )

        starter_accuracy, starter_ranks = validate_results(
            starter_output, query_ids, corpus_ids, ground_truth
        )
        candidate_accuracy, candidate_ranks = validate_results(
            candidate_output, query_ids, corpus_ids, ground_truth
        )
        starter_elapsed = read_duration(starter_time_path)
        candidate_elapsed = read_duration(candidate_time_path)
        time_limit = starter_elapsed * TIME_LIMIT_FRACTION
        time_passed = candidate_elapsed <= time_limit

        if sha256(VECTOR_PATH) != EXPECTED_VECTOR_SHA256:
            raise ValueError("fixed corpus vectors changed during evaluation")

        reward = clamp_reward(candidate_accuracy) if time_passed else 0.0
        report.update(
            {
                "valid": time_passed,
                "reward": reward,
                "primary_metric": {"name": "Accuracy@1", "value": candidate_accuracy},
                "starter_accuracy_at_1": starter_accuracy,
                "candidate_accuracy_at_1": candidate_accuracy,
                "starter_elapsed_seconds": starter_elapsed,
                "candidate_elapsed_seconds": candidate_elapsed,
                "time_limit_seconds": time_limit,
                "time_passed": time_passed,
                "starter_hit_at_1_count": sum(rank == 1 for rank in starter_ranks),
                "candidate_hit_at_1_count": sum(rank == 1 for rank in candidate_ranks),
                "starter_report": read_starter_report(starter_report_path),
                "reward_formula": "clamp((candidate_accuracy_at_1 - 0.31) / 0.69, 0, 1) if candidate_time <= starter_time * 0.60 else 0",
                "fixed_vector_sha256": EXPECTED_VECTOR_SHA256,
            }
        )
        if not time_passed:
            report["errors"] = [
                f"candidate runtime {candidate_elapsed:.6f}s exceeds 60% of starter runtime {starter_elapsed:.6f}s"
            ]
    except Exception as error:
        report["errors"] = [str(error)]
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_report(report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
