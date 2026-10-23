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
