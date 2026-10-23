"""Deterministic true-reference construction; invoked only by the trusted grader."""
import numpy as np

from metrics import PROPERTIES


def feasible(properties, constraints):
    mask = np.ones(len(properties), dtype=bool)
    for name, (lower, upper) in constraints.items():
        if lower is None and upper is None:
            continue
        values = properties[:, PROPERTIES.index(name)]
        mask &= np.isfinite(values)
        if lower is not None:
            mask &= values >= lower
        if upper is not None:
            mask &= values <= upper
    return mask


def top_ids(scores, mask, k=10000):
    ids = np.flatnonzero(mask & np.isfinite(scores))
    values = scores[ids]
    if len(ids) > k:
        boundary = np.partition(values, k - 1)[k - 1]
        below = ids[values < boundary]
        tied = ids[values == boundary][:k - len(below)]
        ids = np.concatenate((below, tied))
    return ids[np.lexsort((ids, scores[ids]))]
