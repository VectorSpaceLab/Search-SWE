from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import faiss
import numpy as np

from common import encode_queries, query_id, query_text, read_jsonl


EXPECTED_VECTOR_SHA256 = "54c2f4a5a83e43d8ab5569f195c7e478a0807c9018e0749a9f62158656c8cd46"
SEARCH_DIMENSION = 2560


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-vectors", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("/task/data/corpus.jsonl"))
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--top-k", type=int, default=1)
    args = parser.parse_args()
    if args.top_k <= 0:
        raise ValueError("top-k must be positive")

    if sha256(args.doc_vectors) != EXPECTED_VECTOR_SHA256:
        raise ValueError("fixed corpus vector checksum does not match the task asset")
    vectors = np.load(args.doc_vectors, mmap_mode="r")
    corpus = read_jsonl(args.corpus)
    doc_ids = [str(row.get("id", row.get("_id", row.get("doc_id", "")))) for row in corpus]
    if not doc_ids or len(set(doc_ids)) != len(doc_ids) or any(not value for value in doc_ids):
        raise ValueError("corpus IDs are missing or duplicated")
    if vectors.shape != (len(doc_ids), SEARCH_DIMENSION) or vectors.dtype != np.float32:
        raise ValueError(f"unexpected fixed vectors: shape={vectors.shape}, dtype={vectors.dtype}")
    if not np.isfinite(vectors[:]).all():
        raise ValueError("fixed corpus vectors contain non-finite values")
    index = faiss.IndexFlatIP(SEARCH_DIMENSION)
    index.add(np.ascontiguousarray(vectors, dtype=np.float32))

    queries = read_jsonl(args.queries)
    started = time.perf_counter()
    query_vectors = encode_queries([query_text(row) for row in queries])
    if query_vectors.shape[1] != index.d:
        raise ValueError(f"unexpected query vector shape: {query_vectors.shape}")
    if not np.isfinite(query_vectors).all():
        raise ValueError("query vectors contain non-finite values")
    fetch_k = min(index.ntotal, args.top_k + 1)
    scores, indices = index.search(query_vectors, fetch_k)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_name(args.output.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        ranked_results: list[list[dict[str, float | str]]] = []
        for row, query_scores, query_indices in zip(queries, scores, indices):
            current_query_id = query_id(row)
            ranked = []
            for score, index in sorted(
                zip(query_scores.tolist(), query_indices.tolist()),
                key=lambda item: (-float(item[0]), int(item[1])),
            ):
                if index < 0 or doc_ids[int(index)] == current_query_id:
                    continue
                ranked.append({"doc_id": doc_ids[int(index)], "score": float(score)})
                if len(ranked) == args.top_k:
                    break
            results = [
                {"doc_id": result["doc_id"], "score": result["score"]}
                for result in ranked
            ]
            if len(results) != args.top_k:
                raise ValueError(f"{current_query_id}: insufficient search results")
            ranked_results.append(results)
            handle.write(json.dumps({"query_id": current_query_id, "results": results}, ensure_ascii=False) + "\n")
    os.replace(temp_path, args.output)
    elapsed_seconds = time.perf_counter() - started
    report = {
        "doc_vectors": str(args.doc_vectors),
        "corpus": str(args.corpus),
        "query_model": "/task/models/Qwen3-Embedding-4B",
        "pooling_method": "last_token",
        "doc_vector_dimension": 2560,
        "query_count": len(queries),
        "top_k": args.top_k,
        "elapsed_seconds": elapsed_seconds,
        "queries_per_second": len(queries) / elapsed_seconds if elapsed_seconds else 0.0,
    }
    if args.ground_truth is not None:
        ground_truth = {
            str(row["query_id"]): [str(value) for value in row["relevant_doc_ids"]]
            for row in read_jsonl(args.ground_truth)
        }
        hits = 0
        for row, results in zip(queries, ranked_results):
            relevant = set(ground_truth.get(query_id(row), []))
            top_doc_id = str(results[0]["doc_id"]) if results else ""
            hits += int(top_doc_id in relevant)
        report.update(
            {
                "hit_at_1_count": hits,
                "accuracy_at_1": hits / len(queries) if queries else 0.0,
            }
        )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temp_report = args.report.with_name(args.report.name + ".tmp")
        temp_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_report, args.report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
