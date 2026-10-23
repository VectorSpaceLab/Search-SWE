"""ARQMath Task 2: visual deduplication, judged-only ranks, linear gain."""
from collections import defaultdict
import math


def read_qrels(path):
    result = defaultdict(dict)
    for line in path.read_text().splitlines():
        qid, _, visual, relevance = line.split()
        visual, relevance = int(visual), int(relevance)
        if relevance not in range(4) or visual in result[qid]:
            raise ValueError('Invalid official qrels')
        result[qid][visual] = relevance
    return dict(result)


def evaluate(response, query_id, mapping, qrels):
    zero = {'ndcg_prime': 0.0, 'map_prime': 0.0, 'p_prime_10': 0.0, 'valid': False}
    if not isinstance(response, dict) or response.get('query_id') != query_id:
        return {**zero, 'error': 'response or query_id'}
    rows = response.get('results')
    if not isinstance(rows, list) or len(rows) > 1000:
        return {**zero, 'error': 'result count/type'}
    scored = []
    for row in rows:
        if not isinstance(row, dict):
            return {**zero, 'error': 'result type'}
        fid, score = row.get('formula_id'), row.get('score')
        if not isinstance(fid, str) or not fid.isascii() or not fid.isdecimal():
            return {**zero, 'error': 'formula_id must be a decimal string'}
        try:
            finite = not isinstance(score, bool) and isinstance(score, (int, float)) and math.isfinite(score)
        except OverflowError:
            finite = False
        if not finite:
            return {**zero, 'error': 'nonfinite or nonnumeric score'}
        # Huge decimal IDs are unknown, without unbounded integer parsing.
        canonical_id = fid.lstrip('0') or '0'
        scored.append((int(canonical_id) if len(canonical_id) < 20 else len(mapping), score))
    # Python's stable sort preserves output order for equal scores.
    scored.sort(key=lambda r: -r[1])
    seen, grades = set(), []
    for fid, _ in scored:
        if fid >= len(mapping) or mapping[fid] < 0:
            continue
        visual = int(mapping[fid])
        if visual in seen:
            continue
        seen.add(visual)
        if visual in qrels:
            grades.append(qrels[visual])
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(grades))
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(qrels.values(), reverse=True)))
    if ideal <= 0:
        raise ValueError('Official query has no positive ideal gain')
    relevant = sum(g >= 2 for g in qrels.values())
    hits, ap = 0, 0.0
    for i, g in enumerate(grades, 1):
        if g >= 2:
            hits += 1
            ap += hits / i
    return {'ndcg_prime': dcg / ideal, 'map_prime': ap / relevant if relevant else 0.0,
            'p_prime_10': sum(g >= 2 for g in grades[:10]) / 10,
            'valid': True, 'judged_returned': len(grades), 'returned': len(rows)}
