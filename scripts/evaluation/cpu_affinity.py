"""Per-run CPU selection and equivalent Compose quota representation."""

import copy
import os
import re


def parse_cpu_set(value):
    if not isinstance(value, str):
        raise ValueError("CPU sets must be a string of IDs or ranges")
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


def normalize_compose_cpu_quota(document, cpus):
    """Preserve explicit CFS limits without also applying Harbor's NanoCPU limit."""
    result = copy.deepcopy(document)
    main = result.get("services", {}).get("main", {})
    if cpus is None or not ({"cpu_period", "cpu_quota"} & main.keys()):
        return result
    period, quota = main.get("cpu_period"), main.get("cpu_quota")
    # Only accept the same budget and period as Harbor's default CPU limit.
    if (type(period) is not int or type(quota) is not int or period != 100_000
            or quota != cpus * period or float(main.get("cpus", cpus)) not in (0, cpus)):
        raise ValueError("Explicit CFS quota must match Harbor's CPU budget at the 100 ms period")
    # Some Compose versions ignore `cpus`. Keep the explicit CFS limit and
    # clear the equivalent NanoCPU field from Harbor's earlier overlay;
    # Docker rejects two nonzero limits even when their budgets agree.
    main["cpus"] = 0
    return result
