#!/usr/bin/env python3
"""Validate Task-2-4 document rankings and compute macro Gold Recall@5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TOP_K = 5
METRIC_NAME = "GoldRecall@5"


def load_queries(path: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"invalid query record at line {line_number}")
            query_id = record.get("query_id")
            question = record.get("question")
            if (
                not isinstance(query_id, str) or not query_id.strip()
                or query_id in queries
                or not isinstance(question, str) or not question.strip()
            ):
                raise ValueError(f"invalid query record at line {line_number}")
            queries[query_id] = question
    if not queries:
        raise ValueError("queries file is empty")
    return queries


def load_qrels(path: Path) -> dict[str, set[str]]:
    gold: dict[str, set[str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 4 or fields[1] not in {"0", "Q0"} or fields[3] != "1":
                raise ValueError(f"invalid gold relevance label at line {line_number}")
            query_id, _, doc_id, _ = fields
            documents = gold.setdefault(query_id, set())
            if doc_id in documents:
                raise ValueError(f"duplicate gold relevance label at line {line_number}")
            documents.add(doc_id)
    if not gold:
        raise ValueError("gold relevance file is empty")
    if any(not 1 <= len(documents) <= TOP_K for documents in gold.values()):
        raise ValueError("each query must have 1-5 gold documents")
    return gold


def load_corpus_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            doc_id = record.get("docid") if isinstance(record, dict) else None
            if not isinstance(doc_id, str) or not doc_id.strip():
                raise ValueError(f"invalid corpus document ID at line {line_number}")
            ids.add(doc_id)
    if len(ids) < TOP_K:
        raise ValueError("corpus must contain at least 5 distinct document IDs")
    return ids


def load_predictions(path: Path, expected: set[str]) -> tuple[dict[str, list[str]], list[str]]:
    predictions: dict[str, list[str]] = {}
    errors: list[str] = []
    try:
        handle = path.open(encoding="utf-8")
    except OSError as error:
        return {}, [f"cannot open predictions: {error}"]
    with handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append(f"line {line_number}: invalid JSON: {error}")
                continue
            if not isinstance(record, dict):
                errors.append(f"line {line_number}: result must be an object")
                continue
            query_id = record.get("query_id")
            if not isinstance(query_id, str) or query_id not in expected:
                errors.append(f"line {line_number}: missing or unknown query_id {query_id!r}")
                continue
            if query_id in predictions:
                errors.append(f"line {line_number}: duplicate query_id {query_id!r}")
                continue
            doc_ids = record.get("doc_ids")
            if (
                not isinstance(doc_ids, list) or len(doc_ids) != TOP_K
                or any(not isinstance(doc_id, str) or not doc_id.strip() for doc_id in doc_ids)
            ):
                errors.append(f"line {line_number}: doc_ids must contain exactly 5 non-empty strings")
                continue
            if len(set(doc_ids)) != TOP_K:
                errors.append(f"line {line_number}: doc_ids must contain 5 distinct document IDs")
                continue
            predictions[query_id] = doc_ids
    missing = sorted(expected - set(predictions))
    if missing:
        errors.append(f"missing outputs for {len(missing)} queries: {missing[:10]}")
    return predictions, errors


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        queries = load_queries(args.queries)
        gold = load_qrels(args.qrels)
        if set(queries) != set(gold):
            raise ValueError("query and gold relevance IDs do not match")
    except (OSError, ValueError) as error:
        write_report(args.report, {"valid": False, "score": 0.0, "errors": [str(error)]})
        return 2

    predictions, errors = load_predictions(args.predictions, set(queries))
    if errors:
        write_report(args.report, {"valid": False, "score": 0.0, "errors": errors})
        return 1

    try:
        corpus_ids = load_corpus_ids(args.corpus)
        if any(not documents <= corpus_ids for documents in gold.values()):
            raise ValueError("gold relevance labels reference documents outside the corpus")
    except (OSError, ValueError) as error:
        write_report(args.report, {"valid": False, "score": 0.0, "errors": [str(error)]})
        return 2
    for query_id, doc_ids in predictions.items():
        unknown = sorted(set(doc_ids) - corpus_ids)
        if unknown:
            errors.append(f"query {query_id}: unknown corpus document IDs: {unknown}")
    if errors:
        write_report(args.report, {"valid": False, "score": 0.0, "errors": errors})
        return 1

    per_query = []
    for query_id in queries:
        hit_count = len(set(predictions[query_id]) & gold[query_id])
        gold_count = len(gold[query_id])
        per_query.append({
            "query_id": query_id,
            "gold_count": gold_count,
            "retrieved_gold_count": hit_count,
            "gold_recall_at_5": hit_count / gold_count,
        })
    recall = sum(item["gold_recall_at_5"] for item in per_query) / len(per_query)
    write_report(args.report, {
        "valid": True,
        "score": 100.0 * recall,
        "query_count": len(per_query),
        "primary_metric": {"name": METRIC_NAME, "value": recall},
        "per_query_metrics": per_query,
        "errors": [],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
