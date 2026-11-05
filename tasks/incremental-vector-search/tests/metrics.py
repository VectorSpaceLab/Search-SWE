"""Pure grading rules. Every dataset has independent stage/K time gates."""
import math

KS = (100, 200, 400, 800, 1000)
TOTAL_NEIGHBORS = 10 * 1000 * sum(KS)


def missing_neighbors(cells):
    return sum(sum((cell["k"] - hits) * count
               for hits, count in enumerate(cell["recall_histogram"])) for cell in cells)


def error_gain(missing, baseline):
    """Logarithmic reduction of actual missed exact neighbors."""
    if type(baseline) is not int or baseline <= 0:
        raise ValueError("Baseline must have a positive measured error count")
    if type(missing) is not int or missing < 0:
        raise ValueError("Invalid measured error count")
    return min(1.0, max(0.0, 1.0 - math.log1p(missing) / math.log1p(baseline)))


def recall(response, truth, k, live_count, tie_ids=()):
    if not isinstance(response, dict):
        return 0.0
    ids, distances = response.get("ids"), response.get("distances")
    if not isinstance(ids, list) or not isinstance(distances, list):
        return 0.0
    if len(ids) != len(distances) or len(ids) > k:
        return 0.0
    # A missing result remains a miss. Each legal ID can contribute at most once.
    valid = set()
    for identifier, distance in zip(ids, distances):
        if type(identifier) is not int or not 0 <= identifier < live_count:
            continue
        if type(distance) not in (int, float) or distance < 0:
            continue
        try:
            if not math.isfinite(distance):
                continue
        except OverflowError:
            continue
        valid.add(identifier)
    acceptable = set(int(i) for i in truth[:k]) | set(tie_ids)
    return len(valid.intersection(acceptable)) / k


def dataset_score(cells, stages=10, ks=KS):
    expected = {(stage, k) for stage in range(stages) for k in ks}
    if len(cells) != len(expected) or {(c["stage"], c["k"]) for c in cells} != expected:
        return 0.0
    for cell in cells:
        values = (cell["seconds"], cell["budget_seconds"], cell["recall"])
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
            return 0.0
        if not 0 <= cell["seconds"] <= cell["budget_seconds"] or cell["budget_seconds"] <= 0:
            return 0.0
        if not 0 <= cell["recall"] <= 1:
            return 0.0
    return sum(c["recall"] for c in cells) / len(expected)


def median_record(records, field='seconds'):
    """Missing/aborted timings are infinite, never omitted from the five samples."""
    def duration(record):
        value = record.get(field) if record is not None else None
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else math.inf
    ordered = sorted(enumerate(records), key=lambda pair: (duration(pair[1]), pair[0]))
    _, record = ordered[len(ordered) // 2]
    return record, duration(record)


def aggregate_replays(replays, limits, *, stages=10, batch_size=1000, ks=KS):
    """Median timing gates; quality comes from the corresponding median-time run."""
    if len(replays) != 5:
        raise ValueError('Exactly five independent replays are required')
    result = {'score': 0.0, 'cells': [], 'replays': replays, 'insert_seconds': []}
    if any(r.get('failure_kind') == 'invalid_submission' for r in replays):
        result['failure'] = 'Invalid execution or resource violation in a replay'
        return result
    _, build = median_record(replays, 'build_seconds')
    result['build_seconds'] = build if math.isfinite(build) else None
    if build > limits['build_seconds']:
        result['failure'] = 'Median build time exceeded its budget'
        return result
    for stage in range(stages):
        records = [{'seconds': r.get('insert_seconds', [])[stage]}
                   if len(r.get('insert_seconds', [])) > stage else None for r in replays]
        _, seconds = median_record(records)
        result['insert_seconds'].append(seconds if math.isfinite(seconds) else None)
        if seconds > limits['insert_seconds']:
            result['failure'] = 'Median insertion time exceeded its budget'
            return result
        for ki, k in enumerate(ks):
            records = [next((c for c in r.get('cells', []) if (c['stage'], c['k']) == (stage, k)), None)
                       for r in replays]
            selected, seconds = median_record(records)
            budget = .10 * limits['full_scan_seconds'][stage][ki]
            if seconds > budget:
                result['failure'] = f'Median query time exceeded its budget at stage {stage}, K={k}'
                return result
            result['cells'].append({**selected, 'seconds': seconds, 'budget_seconds': budget,
                                    'median_replay': next(i for i, c in enumerate(records) if c is selected)})
    missing = missing_neighbors(result['cells'])
    total = stages * batch_size * sum(ks)
    result.update(missing_neighbors=missing, micro_recall=1 - missing / total,
                  mean_recall=sum(c['recall'] for c in result['cells']) / (stages * len(ks)))
    anchor = limits.get('baseline_missing_neighbors')
    result['score'] = error_gain(missing, anchor) if anchor is not None else result['micro_recall']
    return result
