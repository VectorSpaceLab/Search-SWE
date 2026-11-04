#!/usr/bin/env python3
"""Quality and same-host starter-relative latency grader for Task sparse-retrieval-pruning."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


OUTPUT_K = 100
QUALITY_K = 10
EPSILON = 1e-12
MIN_NDCG = 0.89
MIN_RECALL = 0.99
ZERO_REWARD_SPEEDUP = 4.0
FULL_REWARD_SPEEDUP = 16.0
ROUND_COUNT = 5
REWARD_METRIC = "quality_gated_linear_starter_speedup"


def speedup_reward(speedup: float) -> float:
    if not math.isfinite(speedup) or speedup <= 0:
        raise ValueError("speedup must be positive and finite")
    return max(0.0, min(1.0, (speedup - ZERO_REWARD_SPEEDUP) /
                        (FULL_REWARD_SPEEDUP - ZERO_REWARD_SPEEDUP)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in ("rounds", "qrels", "queries", "corpus-ids", "reference", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
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
            raw_score = item.get("score")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise ValueError(f"score must be numeric for {query_id}")
            score = float(raw_score)
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


def grade_rounds(rounds, ids, valid_docs, qrels, reference):
    if len(rounds) != ROUND_COUNT:
        raise ValueError(f"expected {ROUND_COUNT} complete measurement rounds")
    measured = []
    for number, row in enumerate(rounds, 1):
        expected_order = ["starter", "candidate"] if number % 2 else ["candidate", "starter"]
        if row.get("round") != number or row.get("order") != expected_order:
            raise ValueError("measurement rounds/order do not match the protocol")
        result = {"round": number, "order": expected_order}
        for side in ("candidate", "starter"):
            entry = row[side]
            metrics = json.loads(Path(entry["metrics"]).read_text())
            seconds = metrics.get("wall_seconds")
            if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                    or not math.isfinite(seconds) or seconds <= 0):
                raise ValueError("starter and candidate wall_seconds must be positive and finite")
            if metrics.get("return_code") != 0 or metrics.get("error"):
                raise ValueError(f"round {number} {side} execution failed: {metrics.get('error')}")
            rankings = validate_results(load_jsonl(Path(entry["results"])), ids, valid_docs)
            quality, per_query = retrieval_quality(rankings, qrels, ids)
            result[side] = {"quality": quality, "per_query": per_query, "metrics": metrics}
        measured.append(result)
    candidate_quality = {m: statistics.mean(r["candidate"]["quality"][m] for r in measured)
                         for m in ("ndcg@10", "qrels_recall@100")}
    starter_quality = {m: statistics.mean(r["starter"]["quality"][m] for r in measured)
                       for m in candidate_quality}
    floors = {m: all(r["candidate"]["quality"][m] >= minimum for r in measured)
              for m, minimum in (("ndcg@10", MIN_NDCG), ("qrels_recall@100", MIN_RECALL))}
    candidate_seconds = statistics.median(r["candidate"]["metrics"]["wall_seconds"] for r in measured)
    starter_seconds = statistics.median(r["starter"]["metrics"]["wall_seconds"] for r in measured)
    speedup = starter_seconds / candidate_seconds
    latency_score = speedup_reward(speedup)
    reward = latency_score if all(floors.values()) else 0.0
    reference_quality, _ = retrieval_quality(reference, qrels, ids)
    return {
        "status": "ok", "reward_metric": REWARD_METRIC, "reward": reward,
        "score": 100 * reward, "success": reward > 0,
        "quality": {"candidate": candidate_quality, "corrected_starter": starter_quality,
                    "weighted_reference": reference_quality,
                    "thresholds": {"min_ndcg@10": MIN_NDCG, "min_qrels_recall@100": MIN_RECALL},
                    "floors": floors, "aggregation": "mean across rounds; every round must pass"},
        "latency": {"candidate_wall_seconds": candidate_seconds,
                    "starter_wall_seconds": starter_seconds,
                    "speedup": speedup, "ratio": candidate_seconds / starter_seconds,
                    "zero_reward_speedup": ZERO_REWARD_SPEEDUP,
                    "full_reward_speedup": FULL_REWARD_SPEEDUP, "reward": latency_score,
                    "aggregation": "ratio of median wall times from five rounds",
                    "warmup": "none; OS file cache retained; fresh process and scratch each invocation"},
        "rounds": measured,
    }


def main() -> int:
    args = parse_args()
    try:
        ids = query_ids(args.queries)
        valid_docs = load_corpus_ids(args.corpus_ids)
        qrels = load_qrels(args.qrels)
        reference = validate_results(load_jsonl(args.reference), ids, valid_docs)
        report = grade_rounds(json.loads(args.rounds.read_text()), ids, valid_docs, qrels, reference)
        status = 0
    except Exception as exc:
        report = {"status": "invalid", "reward_metric": REWARD_METRIC, "reward": 0.0,
                  "score": 0.0, "error": f"{type(exc).__name__}: {exc}"}
        status = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rounds"}, indent=2, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
