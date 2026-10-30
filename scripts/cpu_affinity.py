"""Per-run logical CPU selection without changing task CPU quotas."""

import copy
import os
import re


def parse_cpu_set(value):
    selected = set()
    for item in value.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", item):
            raise ValueError("CPU sets contain IDs or ranges, for example 0-3,8-11")
        bounds = list(map(int, item.split("-")))
        first, last = bounds[0], bounds[-1]
        if last < first or last > 1_000_000:
            raise ValueError("Invalid CPU range")
        selected.update(range(first, last + 1))
    return selected


def validate_cpu_set(value, count, *, check_host=True):
    selected = parse_cpu_set(value)
    if len(selected) != count:
        raise ValueError(f"This task requires exactly {count} logical CPUs")
    if check_host and not selected <= os.sched_getaffinity(0):
        raise ValueError("Requested CPUs are outside this process's available affinity")
    return ",".join(map(str, sorted(selected)))


def select_compose_cpus(document, value):
    parse_cpu_set(value)
    result = copy.deepcopy(document)
    for service in result["services"].values():
        service["cpuset"] = value
    return result
