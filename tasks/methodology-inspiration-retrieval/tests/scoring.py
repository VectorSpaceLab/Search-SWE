"""Deterministic output validation and macro Recall@3 improvement."""
import json
import math

BASELINE = 0.310109


class VerificationError(ValueError):
    pass


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise VerificationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise VerificationError(f"Non-finite JSON constant: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def validate_row(row, query_id, corpus_order, top_k=3):
    if not isinstance(row, dict) or row.get("query_id") != query_id:
        raise VerificationError("Missing or mismatched query_id")
    results = row.get("results")
    if not isinstance(results, list) or len(results) > top_k:
        raise VerificationError(f"results must contain at most {top_k} items")
    ids, previous = [], None
    for item in results:
        if not isinstance(item, dict):
            raise VerificationError("Result item is not an object")
        doc_id, score = item.get("doc_id"), item.get("score")
        if not isinstance(doc_id, str) or doc_id not in corpus_order:
            raise VerificationError("Unknown document ID")
        if doc_id in ids:
            raise VerificationError("Duplicate document ID")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise VerificationError("Score must be numeric")
        try:
            number = float(score)
        except (OverflowError, ValueError):
            raise VerificationError("Score is not finite")
        if not math.isfinite(number):
            raise VerificationError("Score is not finite")
        key = (-number, corpus_order[doc_id])
        if previous is not None and key < previous:
            raise VerificationError("Results must be score-descending; ties use corpus order")
        previous = key
        ids.append(doc_id)
    return ids


def recall_at_3(ids, relevant):
    if not relevant:
        raise VerificationError("Reference relevant set is empty")
    return len(set(ids[:3]) & set(relevant)) / len(relevant)


def recall_ceiling(gold):
    if not gold or any(not relevant for relevant in gold.values()):
        raise VerificationError("Reference relevant set is empty")
    return math.fsum(min(3, len(relevant)) / len(relevant)
                     for relevant in gold.values()) / len(gold)


def normalized_reward(raw, upper):
    if not math.isfinite(raw) or not BASELINE < upper <= 1 or not 0 <= raw <= upper + 1e-12:
        raise VerificationError("Invalid recall or normalization bound")
    return max(0.0, min(1.0, (raw - BASELINE) / (upper - BASELINE)))
