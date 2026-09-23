"""Independent result validation. Never import submitted modules here."""
import math

import numpy as np


def check_result(query, result, gold, vectors, metadata):
    qid = query["query_id"]
    if not isinstance(result, dict) or result.get("query_id") != qid:
        raise ValueError(f"{qid}: missing or incorrect query_id")
    results = result.get("results")
    expected = min(query["k"], gold["eligible_count"])
    if not isinstance(results, list) or len(results) != expected:
        raise ValueError(f"{qid}: expected exactly {expected} results")
    ids, actual_distances = [], []
    wanted_tags = set(query["filter"]["all"])
    q = np.asarray(query["vector"], dtype=np.float64)
    for item in results:
        if not isinstance(item, dict):
            raise ValueError(f"{qid}: result entry must be an object")
        doc_id, distance = item.get("doc_id"), item.get("distance")
        if type(doc_id) is not int or not 0 <= doc_id < len(vectors) or doc_id in ids:
            raise ValueError(f"{qid}: invalid, duplicate, or out-of-range doc_id")
        if type(distance) not in (int, float) or not math.isfinite(distance):
            raise ValueError(f"{qid}: distance must be finite and numeric")
        start, end = metadata.indptr[doc_id:doc_id + 2]
        present = set(metadata.indices[start:end][metadata.data[start:end] != 0].tolist())
        if not wanted_tags.issubset(present):
            raise ValueError(f"{qid}: result violates the filter")
        delta = np.asarray(vectors[doc_id], dtype=np.float64) - q
        actual = float(np.dot(delta, delta))
        if abs(float(distance) - actual) > 0.001:
            raise ValueError(f"{qid}: returned distance is not accurate squared L2")
        ids.append(doc_id)
        actual_distances.append(actual)
    keys = list(zip(actual_distances, ids))
    if keys != sorted(keys):
        raise ValueError(f"{qid}: results must be sorted by (distance, doc_id)")
    if expected == 0:
        return 1.0
    distances = gold["distances"]
    if len(distances) != expected:
        raise ValueError("invalid private ground-truth cardinality")
    cutoff = distances[-1]
    strict_count = sum(d < cutoff for d in distances)
    strict_hits = sum(d < cutoff - 1e-6 for d in actual_distances)
    boundary_hits = sum(abs(d - cutoff) <= 1e-6 for d in actual_distances)
    # Any equally distant neighbor at the Top-K boundary receives credit.
    return min(expected, strict_hits + min(expected - strict_count, boundary_hits)) / expected
