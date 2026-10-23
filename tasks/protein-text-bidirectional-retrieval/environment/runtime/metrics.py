"""Strict official-pair metrics, retaining failed requests in every denominator."""
import math


def percentile(values, q):
    if not values:
        raise ValueError("No latency observations")
    return sorted(values)[math.ceil(q * len(values)) - 1]


def summarize(records):
    if not records:
        raise ValueError("No queries")
    latencies = [r["seconds"] if r["valid"] else 3.0 for r in records]
    return {
        "queries": len(records), "valid_queries": sum(r["valid"] for r in records),
        "timeouts": sum(r.get("timeout", False) for r in records),
        "recall_at_20": sum(r["hit20"] for r in records) / len(records),
        "accuracy_at_1": sum(r["hit1"] for r in records) / len(records),
        "p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
        "p99": percentile(latencies, .99), "max": max(latencies),
        "latency_gate": percentile(latencies, .95) <= 1.0,
    }


def paired_top1(pairs, protein_to_text, text_to_protein):
    """A pair succeeds only if its two independently scored queries succeed."""
    if not pairs or len(set(pairs.values())) != len(pairs):
        raise ValueError('Expected nonempty one-to-one official pairs')
    for records, expected in [(protein_to_text, set(pairs)), (text_to_protein, set(pairs.values()))]:
        if len(records) != len(pairs) or {r['query_id'] for r in records} != expected:
            raise ValueError('Every official paired query must occur exactly once')
    forward = {r['query_id'] for r in protein_to_text if r['valid'] and r['hit1']}
    backward = {r['query_id'] for r in text_to_protein if r['valid'] and r['hit1']}
    correct = sum(p in forward and t in backward for p, t in pairs.items())
    return {'pairs': len(pairs), 'mutual_top1_correct': correct,
            'mutual_top1_accuracy': correct / len(pairs)}


def paired_quality(datasets):
    if len(datasets) != 2:
        raise ValueError('Expected both datasets')
    for data in datasets:
        if not 0 <= data['mutual_top1_correct'] <= data['pairs'] or data['pairs'] <= 0:
            raise ValueError('Invalid paired success counts')
    return sum(d['mutual_top1_correct'] / d['pairs'] for d in datasets) / 2


def score(groups, datasets):
    if len(groups) != 4 or not all(g["latency_gate"] for g in groups):
        return 0.0
    return paired_quality(datasets)
