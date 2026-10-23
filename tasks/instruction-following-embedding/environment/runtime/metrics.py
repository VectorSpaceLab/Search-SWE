"""FollowIR metrics; MTEB 1.12.90 commit 7a5f501843c3881201710700249776ab39c7fe75.

p-MRR is equivalent to utils.rank_score/evaluate_change, with a fixed query
 denominator even for failed pairs. Ties retain upstream candidate order.
"""
import math
import numpy as np

SUBSETS = ('robust04', 'core17', 'news21')
SCORING_METRIC = 'harmonic-subset-pmrr'


def harmonic_pmrr(values):
    """Require positive instruction-following changes in every subset."""
    values = tuple(values)
    if len(values) != 3 or not all(math.isfinite(v) and -1 <= v <= 1 for v in values):
        raise ValueError('Expected three finite subset p-MRR values in [-1,1]')
    smallest = min(values)
    if smallest <= 0:
        return 0.
    # Equivalent to 3/sum(1/v), without reciprocal overflow near zero.
    return 3 * smallest / math.fsum(smallest / v for v in values)


def pmrr(original, changed, changed_ids, size=1000):
    if not changed_ids:
        raise ValueError('A query must have changed relevance judgments')
    a = {d: i + 1 for i, d in enumerate(original)}
    b = {d: i + 1 for i, d in enumerate(changed)}
    values = []
    for doc in changed_ids:
        x, y = a.get(doc, size + 1), b.get(doc, size + 1)
        values.append(y / x - 1 if x >= y else 1 - x / y)
    return math.fsum(values) / len(values)


def ndcg(ranking, qrels, k=10):
    # trec_eval linear gains, IDCG from all original judgments.
    gains = sorted((max(0., float(x)) for x in qrels.values()), reverse=True)[:k]
    ideal = math.fsum(g / math.log2(i + 2) for i, g in enumerate(gains))
    actual = math.fsum(max(0., float(qrels.get(d, 0))) / math.log2(i + 2)
                       for i, d in enumerate(ranking[:k]))
    return actual / ideal if ideal else 0.


def average_precision(ranking, qrels):
    relevant = {d for d, v in qrels.items() if v > 0}
    hits, terms = 0, []
    for i, d in enumerate(ranking, 1):
        if d in relevant:
            hits += 1
            terms.append(hits / i)
    return math.fsum(terms) / len(relevant) if relevant else 0.


def rank_vectors(query, documents, candidate_ids):
    q = np.asarray(query, dtype=np.float32)
    if q.shape != (1024,) or not np.isfinite(q).all() or np.linalg.norm(q) == 0:
        raise ValueError('Expected finite nonzero 1024-dimensional query vector')
    q = q / np.linalg.norm(q)
    d = np.asarray(documents, dtype=np.float32)
    if d.shape != (len(candidate_ids), 1024) or not np.isfinite(d).all():
        raise ValueError('Invalid document vectors')
    lengths = np.linalg.norm(d, axis=1)
    if np.any(lengths == 0):
        raise ValueError('Zero document vector')
    scores = (d / lengths[:, None]) @ q
    return [candidate_ids[i] for i in np.argsort(-scores, kind='stable')]


def evaluate_pairs(groups, rankings):
    rows, subsets = [], {}
    for g in groups:
        key = g['key']
        result = rankings.get(key)
        good = (result is not None and len(result) == 2 and
                all(len(r) == 1000 and len(set(r)) == 1000 and
                    set(r) == set(g['candidates']) for r in result))
        row = {'key': key, 'subset': g['subset'], 'valid': bool(good)}
        row['pmrr'] = pmrr(*result, g['changed_ids']) if good else 0.
        for version, index in [('og', 0), ('changed', 1)]:
            r = result[index] if good else []
            row['ndcg10_' + version] = ndcg(r, g['qrels_' + version])
            row['ndcg5_' + version] = ndcg(r, g['qrels_' + version], 5)
            row['map_' + version] = average_precision(r, g['qrels_' + version])
        rows.append(row)
    if not rows:
        raise ValueError('No query groups')
    fields = ['pmrr', 'ndcg10_og', 'ndcg10_changed', 'ndcg5_og',
              'ndcg5_changed', 'map_og', 'map_changed']
    for subset in SUBSETS:
        sr = [r for r in rows if r['subset'] == subset]
        if not sr:
            raise ValueError('Missing subset: ' + subset)
        subsets[subset] = {f: math.fsum(r[f] for r in sr) / len(sr) for f in fields}
        subsets[subset].update(groups=len(sr), valid=sum(r['valid'] for r in sr))
    return {'P': math.fsum(v['pmrr'] for v in subsets.values()) / 3,
            'H': harmonic_pmrr(subsets[s]['pmrr'] for s in SUBSETS),
            'subsets': subsets, 'rows': rows}


def reward(report, anchors):
    if anchors.get('metric') != SCORING_METRIC:
        raise ValueError('Scoring anchors use a different metric')
    b, u, rho = (anchors[k] for k in ('B', 'U', 'rho'))
    if not all(math.isfinite(v) for v in (b, u, rho)) or not (u > b >= 0 and 0 < rho <= 1):
        raise ValueError('Scoring anchors are not calibrated')
    gates = {s + '/' + v: report['subsets'][s]['ndcg10_' + v] >=
             rho * anchors['R0'][s][v] for s in SUBSETS for v in ('og', 'changed')}
    h = harmonic_pmrr(report['subsets'][s]['pmrr'] for s in SUBSETS)
    score = max(0., min(1., (h - b) / (u - b))) if all(gates.values()) else 0.
    return score, gates
