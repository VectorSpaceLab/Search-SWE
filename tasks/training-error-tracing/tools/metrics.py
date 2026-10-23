"""Prototype deterministic scoring; no invented B/U or production test labels."""

import math
from collections import defaultdict
from statistics import mean


def query_precision(prediction, relevant, valid_ids, elapsed_sec, timeout_sec=10.0):
    """Invalid/late queries score zero; missing slots always count as misses."""
    zero = {"p10": 0.0, "p5": 0.0}
    if (isinstance(elapsed_sec, bool) or not isinstance(elapsed_sec, (int, float))
            or not math.isfinite(elapsed_sec) or elapsed_sec < 0 or elapsed_sec > timeout_sec):
        return {**zero, "status": "timeout-or-invalid-timing"}
    if not isinstance(prediction, list) or len(prediction) > 10:
        return {**zero, "status": "invalid-output"}
    if any(not isinstance(v, str) or v not in valid_ids for v in prediction):
        return {**zero, "status": "invalid-id"}
    if len(set(prediction)) != len(prediction):
        return {**zero, "status": "duplicate-id"}
    return {"p10": sum(v in relevant for v in prediction) / 10,
            "p5": sum(v in relevant for v in prediction[:5]) / 5, "status": "ok"}


def macro_precision(expected_queries, query_results, relevant_by_group, valid_ids, timeout_sec=10.0):
    """Only expected queries define the denominator; missing queries stay in it."""
    grouped = defaultdict(list)
    expected_ids = [q["id"] for q in expected_queries]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Duplicate evaluation query ID")
    if set(query_results) - set(expected_ids):
        raise ValueError("Unexpected result query ID")
    for q in expected_queries:
        group = q["group_id"]
        if len(relevant_by_group[group]) < 10:
            raise ValueError("A formal group needs at least ten relevant records")
        result = query_results.get(q["id"])
        if result is None:
            score = {"p10": 0.0, "p5": 0.0, "status": "missing"}
        else:
            score = query_precision(result["ids"], relevant_by_group[group], valid_ids,
                                    result["elapsed_sec"], timeout_sec)
        grouped[group].append(score)
    if not grouped:
        raise ValueError("No evaluation groups")
    per_group = {g: {"p10": mean(s["p10"] for s in scores),
                     "p5": mean(s["p5"] for s in scores), "queries": len(scores)}
                 for g, scores in grouped.items()}
    return {"Q": mean(v["p10"] for v in per_group.values()),
            "p5": mean(v["p5"] for v in per_group.values()), "groups": per_group}


def normalized_score(quality, baseline, reference):
    values = (quality, baseline, reference)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("Q/B/U must be finite numbers in [0,1]")
    if reference <= baseline:
        raise ValueError("A measured positive reference margin is required")
    return 100 * min(1.0, max(0.0, (quality - baseline) / (reference - baseline)))
