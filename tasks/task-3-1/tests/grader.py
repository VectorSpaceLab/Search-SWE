#!/usr/bin/env python3
"""Quality and same-host starter-relative latency grader for Task-3-1."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


OUTPUT_K = 100
QUALITY_K = 10
EPSILON = 1e-12
MIN_NDCG = 0.89
MIN_RECALL = 0.99
FULL_REWARD_STARTER_WALL_RATIO = 0.30
ZERO_REWARD_STARTER_WALL_RATIO = 0.50
REWARD_METRIC = "quality_gated_linear_starter_latency"


def latency_reward(ratio: float) -> float:
    if ratio <= FULL_REWARD_STARTER_WALL_RATIO:
        return 1.0
    if ratio >= ZERO_REWARD_STARTER_WALL_RATIO:
        return 0.0
    return (ZERO_REWARD_STARTER_WALL_RATIO - ratio) / (
        ZERO_REWARD_STARTER_WALL_RATIO - FULL_REWARD_STARTER_WALL_RATIO
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--baseline-results", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--corpus-ids", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-metadata", type=Path, required=True)
    parser.add_argument("--categories", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--build-metrics", type=Path, required=True)
    parser.add_argument("--run-metrics", type=Path, required=True)
    parser.add_argument("--baseline-run-metrics", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSON object expected at {path}:{line_number}")
            rows.append(row)
    return rows


def query_ids(path: Path) -> list[str]:
    ids = [str(row.get("query_id", row.get("_id", ""))) for row in load_jsonl(path)]
    if not ids or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"invalid query IDs in {path}")
    return ids


def load_corpus_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            doc_id = line.rstrip("\n")
            if not doc_id or doc_id in ids:
                raise ValueError(f"empty or duplicate corpus ID in {path}")
            ids.add(doc_id)
    if not ids:
        raise ValueError(f"empty corpus ID file: {path}")
    return ids


def load_qrels(path: Path) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8") as handle:
        header = next(handle, "").split()
        if header[:3] not in (
            ["query-id", "doc-id", "score"],
            ["query-id", "corpus-id", "score"],
        ):
            raise ValueError(f"invalid qrels header in {path}")
        for line_number, line in enumerate(handle, 2):
            fields = line.split()
            if len(fields) < 3:
                raise ValueError(f"malformed qrels row at {path}:{line_number}")
            query_id, doc_id = fields[:2]
            score = float(fields[2])
            if not math.isfinite(score):
                raise ValueError(f"non-finite qrels score at {path}:{line_number}")
            if doc_id in result.setdefault(query_id, {}):
                raise ValueError(f"duplicate qrel {query_id}/{doc_id}")
            result[query_id][doc_id] = score
    return result


def validate_results(
    rows: list[dict[str, Any]], expected_ids: list[str], valid_docs: set[str]
) -> dict[str, list[str]]:
    if [str(row.get("query_id", "")) for row in rows] != expected_ids:
        raise ValueError("result query IDs or order do not match hidden queries")
    rankings: dict[str, list[str]] = {}
    for query_id, row in zip(expected_ids, rows, strict=True):
        values = row.get("results")
        if not isinstance(values, list) or len(values) > OUTPUT_K:
            raise ValueError(f"invalid result count for {query_id}")
        docs: list[str] = []
        seen: set[str] = set()
        previous_score = math.inf
        previous_doc = ""
        for item in values:
            if not isinstance(item, dict):
                raise ValueError(f"invalid result object for {query_id}")
            doc_id = str(item.get("doc_id", ""))
            score = float(item.get("score"))
            if not doc_id or doc_id not in valid_docs or doc_id in seen or not math.isfinite(score):
                raise ValueError(f"invalid document/score for {query_id}")
            if score > previous_score + EPSILON:
                raise ValueError(f"scores are not descending for {query_id}")
            if abs(score - previous_score) <= EPSILON and previous_doc and doc_id < previous_doc:
                raise ValueError(f"score ties are not doc-ID ordered for {query_id}")
            seen.add(doc_id)
            docs.append(doc_id)
            previous_score = score
            previous_doc = doc_id
        rankings[query_id] = docs
    return rankings


def dcg(gains: list[float]) -> float:
    return sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))


def retrieval_quality(
    rankings: dict[str, list[str]], qrels: dict[str, dict[str, float]], ids: list[str]
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    per_query: dict[str, dict[str, float]] = {}
    for query_id in ids:
        relevant = qrels.get(query_id, {})
        docs = rankings[query_id]
        gains = [relevant.get(doc, 0.0) for doc in docs[:QUALITY_K]]
        ideal = sorted((value for value in relevant.values() if value > 0), reverse=True)[:QUALITY_K]
        ideal_dcg = dcg(ideal)
        ndcg = dcg(gains) / ideal_dcg if ideal_dcg else 0.0
        positive_count = sum(value > 0 for value in relevant.values())
        recall = (
            sum(relevant.get(doc, 0.0) > 0 for doc in docs[:OUTPUT_K]) / positive_count
            if positive_count
            else 0.0
        )
        per_query[query_id] = {"ndcg@10": ndcg, "qrels_recall@100": recall}
    aggregate = {
        metric: sum(row[metric] for row in per_query.values()) / len(ids)
        for metric in ("ndcg@10", "qrels_recall@100")
    }
    return aggregate, per_query


def main() -> int:
    args = parse_args()
    try:
        ids = query_ids(args.queries)
        valid_docs = load_corpus_ids(args.corpus_ids)
        qrels = load_qrels(args.qrels)
        candidate = validate_results(load_jsonl(args.results), ids, valid_docs)
        starter = validate_results(
            load_jsonl(args.baseline_results), ids, valid_docs
        )
        reference = validate_results(load_jsonl(args.reference), ids, valid_docs)
        candidate_quality, per_query = retrieval_quality(candidate, qrels, ids)
        starter_quality, _ = retrieval_quality(starter, qrels, ids)
        reference_quality, _ = retrieval_quality(reference, qrels, ids)
        run_metrics = json.loads(args.run_metrics.read_text(encoding="utf-8"))
        baseline_metrics = json.loads(
            args.baseline_run_metrics.read_text(encoding="utf-8")
        )
        baseline_seconds = float(baseline_metrics.get("wall_seconds", 0.0))
        candidate_seconds = float(run_metrics.get("wall_seconds", 0.0))
        if baseline_seconds <= 0 or candidate_seconds <= 0:
            raise ValueError("starter and candidate wall_seconds must be positive")
        latency_ratio = candidate_seconds / baseline_seconds
        full_reward_candidate_seconds = (
            baseline_seconds * FULL_REWARD_STARTER_WALL_RATIO
        )
        zero_reward_candidate_seconds = (
            baseline_seconds * ZERO_REWARD_STARTER_WALL_RATIO
        )
        floors = {
            "ndcg@10": candidate_quality["ndcg@10"] >= MIN_NDCG,
            "qrels_recall@100": candidate_quality["qrels_recall@100"] >= MIN_RECALL,
        }
        quality_pass = all(floors.values())
        latency_score = latency_reward(latency_ratio)
        reward = latency_score if quality_pass else 0.0
        success = quality_pass and reward > 0.0
        report: dict[str, Any] = {
            "status": "ok",
            "reward_metric": REWARD_METRIC,
            "reward": reward,
            "success": success,
            "quality": {
                "candidate": candidate_quality,
                "corrected_starter": starter_quality,
                "weighted_reference": reference_quality,
                "thresholds": {
                    "min_ndcg@10": MIN_NDCG,
                    "min_qrels_recall@100": MIN_RECALL,
                },
                "floors": floors,
                "per_query": per_query,
            },
            "latency": {
                "candidate_wall_seconds": candidate_seconds,
                "starter_wall_seconds": baseline_seconds,
                "full_reward_starter_wall_ratio": FULL_REWARD_STARTER_WALL_RATIO,
                "zero_reward_starter_wall_ratio": ZERO_REWARD_STARTER_WALL_RATIO,
                "full_reward_candidate_wall_seconds": full_reward_candidate_seconds,
                "zero_reward_candidate_wall_seconds": zero_reward_candidate_seconds,
                "ratio": latency_ratio,
                "reward": latency_score,
                "starter_run_metrics": baseline_metrics,
                "run_metrics": run_metrics,
            },
            "ignored_legacy_signals": [
                "exact_top100_overlap",
                "shared_document_score_agreement",
                "index_size",
                "posting_balance",
                "weighted_wand_upper_bound_audit",
            ],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        report = {
            "status": "invalid",
            "reward_metric": REWARD_METRIC,
            "reward": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
