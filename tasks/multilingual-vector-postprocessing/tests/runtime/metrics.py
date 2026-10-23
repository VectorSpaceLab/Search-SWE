"""Deterministic binary nDCG/Recall and dataset/language macro aggregation."""
from collections import defaultdict
import math
import numpy as np


def normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError("Expected a finite 2-D matrix")
    scale = np.max(np.abs(vectors), axis=1, keepdims=True)
    if (scale <= 0).any():
        raise ValueError("Zero vector norm")
    # Cosine is invariant to positive row scaling. Bound FP32 intermediates
    # before summing squares so valid finite outputs cannot overflow/underflow.
    scaled = vectors / scale
    norms = np.linalg.norm(scaled, axis=1, keepdims=True)
    return scaled / norms


def rank(scores, document_ids, k=20):
    scores = np.asarray(scores)
    if scores.shape != (len(document_ids),) or not np.isfinite(scores).all():
        raise ValueError("Invalid score array")
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("Duplicate document IDs")
    # Total ordering includes every candidate so a tie at position k is also
    # resolved by ID; argpartition followed by sorting k items is insufficient.
    return np.lexsort((np.asarray(document_ids), -scores))[:k]


def quality(ranked_ids, relevant_ids, k=20):
    if len(set(ranked_ids)) != len(ranked_ids):
        raise ValueError("Duplicate ranked document ID")
    relevant_ids = set(relevant_ids)
    if not relevant_ids:
        raise ValueError("Empty relevance set")
    dcg = sum(1 / math.log2(i + 2) for i, d in enumerate(ranked_ids[:k]) if d in relevant_ids)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant_ids))))
    recall = len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)
    return dcg / idcg, recall


def aggregate(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["language"])].append(row)
    if {d for d, _ in groups} != {"belebele", "xquad"}:
        raise ValueError("Both evaluation datasets are required")
    expected = {"belebele": {"ar", "zh", "en", "fr", "hi", "it", "ja", "pt", "ru", "es"},
                "xquad": {"ar", "zh", "en", "hi", "ru", "es"}}
    result = {"datasets": {}}
    for dataset, languages in expected.items():
        if {lang for d, lang in groups if d == dataset} != languages:
            raise ValueError("Missing query language; failed queries must remain in the denominator")
        per_language = {}
        for lang in sorted(languages):
            items = groups[dataset, lang]
            for row in items:
                for metric in ("ndcg", "recall"):
                    if not isinstance(row[metric], (int, float)) or not math.isfinite(row[metric]) or not 0 <= row[metric] <= 1:
                        raise ValueError("Invalid metric")
            per_language[lang] = {"queries": len(items),
                                  "valid_queries": sum(bool(x.get("valid", True)) for x in items),
                                  **{metric: sum(x[metric] for x in items) / len(items) for metric in ("ndcg", "recall")}}
        result["datasets"][dataset] = {"languages": per_language,
                                         **{metric: sum(x[metric] for x in per_language.values()) / len(languages)
                                            for metric in ("ndcg", "recall")}}
    result["Q"] = sum(x["ndcg"] for x in result["datasets"].values()) / 2
    return result


def reward(q, baseline, reference):
    if not all(math.isfinite(x) for x in (q, baseline, reference)) or not 0 <= baseline < reference <= 1 or not 0 <= q <= 1:
        raise ValueError("Uncalibrated anchors or invalid quality")
    return max(0., min(1., (q - baseline) / (reference - baseline)))
