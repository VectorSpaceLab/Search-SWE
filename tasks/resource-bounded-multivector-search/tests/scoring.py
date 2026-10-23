"""Deterministic Recall@100 with a fixed denominator and corpus-order ties."""
import math


def normalized_query_seconds(seconds, frozen_baseline_seconds, current_baseline_seconds):
    if any(not math.isfinite(x) or x <= 0
           for x in [seconds, frozen_baseline_seconds, current_baseline_seconds]):
        raise ValueError('Invalid current/frozen baseline timing')
    return seconds * frozen_baseline_seconds / current_baseline_seconds


def recall(response, truth, row_by_id, query_id):
    if not isinstance(response, dict) or type(response.get('query_id')) is not int or response['query_id'] != query_id:
        return 0.0
    results = response.get('results')
    if not isinstance(results, list) or len(results) > 100:
        return 0.0
    valid = set()
    previous = None
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get('doc_id'), str):
            return 0.0
        score = result.get('score')
        if type(score) not in (int, float) or not math.isfinite(score):
            return 0.0
        row = row_by_id.get(result['doc_id'])
        if row is None:
            continue
        key = (-score, row)
        if previous is not None and key < previous:
            return 0.0
        previous = key
        valid.add(row)
    return len(valid.intersection(map(int, truth))) / 100


def gated_reward(recall_sum, count, seconds, baseline_seconds, reference_seconds,
                 resources_ok=True, minimum_recall=0.99):
    if (count <= 0 or not math.isfinite(baseline_seconds) or not math.isfinite(reference_seconds)
            or not 0 < reference_seconds < baseline_seconds
            or not math.isfinite(minimum_recall) or not 0 < minimum_recall <= 1):
        raise ValueError('Missing or invalid frozen speed anchors')
    if (not resources_ok or not math.isfinite(seconds) or seconds <= 0
            or not math.isfinite(recall_sum) or not 0 <= recall_sum <= count):
        return 0.0
    # Per-query recall changes in 0.01 steps. Twelve decimals removes summation
    # noise at exactly 99% without accepting the next smaller possible hit count.
    if round(recall_sum / count, 12) < minimum_recall:
        return 0.0
    return min(1.0, max(0.0, (baseline_seconds-seconds)/(baseline_seconds-reference_seconds)))
