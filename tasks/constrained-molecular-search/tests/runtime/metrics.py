"""Public output validation and deterministic Recall-j-at-k aggregation."""
import math

import numpy as np

K = 10_000
JS = (K,)
TARGETS = ("DRD2", "ESR1", "F10", "MET", "PARP1")
PROPERTIES = ("mol_wt", "logp", "n_hbd", "n_hba", "n_rotatable_bonds", "tpsa")


def validate_ids(ids, n_products, k=K):
    if not isinstance(ids, list) or len(ids) > k:
        raise ValueError("ids must be a list with at most k items")
    if any(type(item) is not int or not 0 <= item < n_products for item in ids):
        raise ValueError("Each ID must be an integer in the library's ordinal range")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate combination IDs")
    return np.asarray(ids, dtype=np.int64)


def recalls(ids, ordered_truth, js=JS):
    truth = np.asarray(ordered_truth, dtype=np.int64)
    if len(truth) < max(js):
        raise ValueError("Main quality queries require complete truth sets")
    found = np.isin(truth[:max(js)], ids, assume_unique=True)
    return [float(found[:j].sum() / j) for j in js]


def summarize(rows):
    by_target = {}
    for target in TARGETS:
        group = [row for row in rows if row["target"] == target and row.get("main", True)]
        if not group:
            raise ValueError(f"No main queries for {target}")
        by_target[target] = float(np.mean([np.mean(row["recalls"]) for row in group]))
    return float(np.mean(list(by_target.values()))), by_target


def reward(q, baseline, reference):
    if not all(math.isfinite(x) for x in (q, baseline, reference)):
        raise ValueError("Nonfinite quality or calibration")
    if not 0 <= baseline < reference <= 1 or not 0 <= q <= 1:
        raise ValueError("Invalid calibration or quality")
    return min(1.0, max(0.0, (q - baseline) / (reference - baseline)))
