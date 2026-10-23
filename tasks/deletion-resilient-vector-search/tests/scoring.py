"""Pure scoring and strict validation; no submission-supplied resource metrics."""
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def recall(response, truth, live, query_id):
    if not isinstance(response, dict) or type(response.get('query_id')) is not int or response['query_id'] != query_id:
        return 0.0
    items = response.get('results')
    if not isinstance(items, list) or len(items) > 10:
        return 0.0
    hits, seen = 0, set()
    for item in items:
        if not isinstance(item, dict):
            return 0.0
        i, distance = item.get('id'), item.get('distance')
        if type(i) is not int or not finite(distance) or distance < 0:
            return 0.0
        if i in seen:
            continue
        seen.add(i)
        if 0 <= i < len(live) and live[i] and i in truth:
            hits += 1
    return hits / 10.0


def dataset_score(stages, initial_memory, reference):
    if not finite(initial_memory) or initial_memory <= 0 or len(stages) != 100:
        raise ValueError('Incomplete or invalid memory measurement')
    b0, bl = reference['initial_rss_bytes'], reference['live_rss_bytes']
    if not finite(b0) or b0 <= 0 or len(bl) != 100 or any(not finite(x) or x <= 0 for x in bl):
        raise ValueError('Invalid HNSW reference')
    gap = b0 - sum(bl) / 100
    if gap <= max(1 << 20, reference['memory_noise_bytes'] * 10):
        raise ValueError('HNSW reference does not exceed measured noise')
    for s in stages:
        if any(not finite(s[k]) for k in ['rss_bytes', 'recall', 'query_seconds']):
            raise ValueError('Nonfinite measurement')
        if s['rss_bytes'] <= 0 or not 0 <= s['recall'] <= 1 or s['query_seconds'] < 0:
            raise ValueError('Invalid stage measurement')
    r = sum(s['recall'] for s in stages) / 100
    baseline = reference.get('recall_baseline', {})
    r0 = baseline.get('recall')
    if baseline.get('status') != 'frozen' or not finite(r0) or not 0 <= r0 < 1:
        raise ValueError('Missing or invalid frozen recall baseline')
    query_count = reference.get('config', {}).get('test_query_count')
    if type(query_count) is not int or query_count <= 0:
        raise ValueError('Invalid query count for log-error normalization')
    positions = query_count * 100 * 10
    # Recover integer hit counts from floating-point averaged recalls.
    errors = round(positions * (1 - r))
    baseline_errors = round(positions * (1 - r0))
    if baseline_errors <= 0:
        raise ValueError('Recall baseline has no measurable retrieval errors')
    gain = min(1.0, max(0.0, 1 - math.log1p(errors) / math.log1p(baseline_errors)))
    memory = sum(s['rss_bytes'] for s in stages) / 100
    e = min(1.0, max(0.0, (b0 - memory) / gap))
    return {'reward': gain * (.8 + .2 * e), 'recall': r, 'recall_baseline': r0,
            'recall_gain': gain, 'recall_errors': errors,
            'baseline_recall_errors': baseline_errors, 'memory_efficiency': e,
            'mean_rss_bytes': memory, 'reclaimed_bytes': initial_memory - stages[-1]['rss_bytes'],
            'reclaimed_fraction': (initial_memory - stages[-1]['rss_bytes']) / initial_memory}


def validate_reference(r):
    if r.get('status') != 'frozen' or r.get('stages') != 100:
        raise ValueError('Reference calibration is not frozen')
    times = r.get('full_scan_seconds', [])
    if len(times) != 100 or any(not finite(x) or x <= 0 for x in times):
        raise ValueError('Missing full-scan stage timing')
    for k in ['build_timeout_seconds', 'delete_timeout_seconds', 'calibration_timeout_seconds', 'memory_noise_bytes']:
        if not finite(r.get(k)) or r[k] <= 0:
            raise ValueError(f'Invalid calibration field: {k}')
    dataset_score([{'rss_bytes': 1, 'recall': 0, 'query_seconds': 0}] * 100, 1, r)
