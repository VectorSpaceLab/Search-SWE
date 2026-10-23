"""Deterministic BEIR-compatible metrics; references must be measured and frozen."""
import math


def ndcg10(ids, qrels):
    ideal = sorted(qrels.values(), reverse=True)[:10]
    denominator = sum((2 ** rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal))
    numerator = sum((2 ** qrels.get(doc, 0) - 1) / math.log2(i + 2)
                    for i, doc in enumerate(ids[:10]))
    return numerator / denominator if denominator else 0.0


def reward(quality, baseline, reference):
    if not all(isinstance(x, (int, float)) and math.isfinite(x)
               and 0 <= x <= 1 for x in (quality, baseline, reference)):
        raise ValueError('Missing or invalid measured Q/B/U')
    if reference <= baseline:
        raise ValueError('Reference must exceed baseline; calibration is incomplete')
    return max(0.0, min(1.0, (quality - baseline) / (reference - baseline)))


def valid_ranking(ids, count):
    if not isinstance(ids, list) or len(ids) > 10:
        return False
    return (all(isinstance(x, str) and 3 < len(x) <= 3+len(str(count-1))
                and x.startswith('doc') and x[3:].isascii() and x[3:].isdigit()
                and x == f'doc{int(x[3:])}' and 0 <= int(x[3:]) < count for x in ids)
            and len(set(ids)) == len(ids))
