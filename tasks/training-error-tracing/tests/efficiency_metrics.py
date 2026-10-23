"""Quality-gated efficiency scoring; anchors require independent calibration."""

import math
from statistics import median


def latency_metric(passes):
    """Equal group weights; median repetitions for every expected query."""
    if not passes:
        raise ValueError("No measured passes")
    first = {row["id"]: row["group_id"] for row in passes[0]}
    if len(first) != len(passes[0]) or not first:
        raise ValueError("Missing or duplicate query IDs")
    timings = {qid: [] for qid in first}
    for rows in passes:
        if len(rows) != len(first) or {r["id"]: r["group_id"] for r in rows} != first:
            raise ValueError("Every repetition must contain all expected queries/groups")
        for row in rows:
            value = row["elapsed_sec"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid measured latency")
            timings[row["id"]].append(value)
    groups = {}
    for qid, samples in timings.items():
        groups.setdefault(first[qid], []).append(median(samples))
    return sum(sum(values)/len(values) for values in groups.values())/len(groups)


def quality_gate(quality_passes, quality_floor=.98, group_floor=.8):
    if not quality_passes:
        raise ValueError("No quality passes")
    for quality in quality_passes:
        values = [quality["Q"], *[row["p10"] for row in quality["groups"].values()]]
        if (len(values) < 2 or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                  or not math.isfinite(x) or not 0 <= x <= 1 for x in values)):
            raise ValueError("Invalid quality measurements")
        if quality["Q"]+1e-12 < quality_floor or min(values[1:])+1e-12 < group_floor:
            return False
    return True


def efficiency_score(quality_passes, latency, memory_bytes, control_latency,
                     control_memory_bytes, reference_cost_ratio, *,
                     quality_floor=.98, group_floor=.8, base_points=20.,
                     noise_ratio=.9, memory_floor_bytes=1024**3):
    """A 20-point quality milestone, then logarithmic latency-memory progress.

    C=(T/T_control)*(M/M_control). Ten-percent cost changes are treated as noise.
    CPU-only systems use the stated one-GiB accounting floor. All queries and
    repetitions remain in quality/latency denominators. No model identity enters
    this function. The reference ratio must be frozen before a coding-model run.
    """
    numeric = [latency, control_latency, memory_bytes, control_memory_bytes,
               reference_cost_ratio, quality_floor, group_floor, base_points, noise_ratio]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in numeric):
        raise ValueError("Nonfinite or invalid scoring inputs")
    if (latency <= 0 or control_latency <= 0 or min(memory_bytes, control_memory_bytes) < 0
            or not 0 < reference_cost_ratio < noise_ratio < 1
            or not 0 < group_floor <= quality_floor <= 1 or not 0 <= base_points <= 100
            or type(memory_floor_bytes) is not int or memory_floor_bytes <= 0):
        raise ValueError("Invalid anchors, measurements or quality floors")
    if not quality_gate(quality_passes, quality_floor, group_floor):
        return {"score": 0., "quality_gate_passed": False, "cost_ratio": None}
    cost = (latency/control_latency)*(max(memory_floor_bytes, memory_bytes)
                                     /max(memory_floor_bytes, control_memory_bytes))
    progress = min(1., max(0., math.log(cost/noise_ratio)/math.log(reference_cost_ratio/noise_ratio)))
    return {"score": base_points+(100-base_points)*progress,
            "quality_gate_passed": True, "cost_ratio": cost,
            "efficiency_progress": progress}
