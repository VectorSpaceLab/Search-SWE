"""Container-side OOM evidence shared by Formula and Bimetric on cgroup v1."""

import json
import socket

if __package__:
    from .cgroup_resources import CgroupError
else:  # Independent task image.
    from cgroup_resources import CgroupError


SOCKET = "/run/search-swe-memory/oom.sock"


def snapshot(memory):
    """Sample the limit counters first so the notification check covers that interval."""
    hits = memory.v1_limit_hits()
    _, counters = memory.memory_events("oom_kill")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(SOCKET)
            with client.makefile("rb") as stream:
                watch = json.loads(stream.readline(4096))
    except (FileNotFoundError, PermissionError, ConnectionError, TimeoutError):
        watch = None  # Raw cgroup counters can still establish some outcomes.
    except (OSError, ValueError) as error:
        raise CgroupError(f"Cannot read v1 OOM observer: {error}") from error
    if watch is not None:
        try:
            info = memory.path.stat()
        except OSError as error:
            raise CgroupError(f"Cannot identify the task memory cgroup: {error}") from error
        if not isinstance(watch, dict) or watch.get("cgroup") != [info.st_dev, info.st_ino]:
            raise CgroupError("Host OOM observer and task see different memory cgroups")
    return {"limit_hits": hits, "oom_kill": counters["oom_kill"], "observer": watch}


def _counter(value):
    return type(value) is int and value >= 0


def _limit_hits(value):
    return (isinstance(value, list) and len(value) == 2 and _counter(value[0])
            and (value[1] is None or _counter(value[1])))


def _validate(sample):
    if (not isinstance(sample, dict) or not _limit_hits(sample.get("limit_hits"))
            or not _counter(sample.get("oom_kill")) or "observer" not in sample):
        raise CgroupError("Invalid v1 memory counters")
    watch = sample["observer"]
    if watch is not None and (not isinstance(watch, dict) or not isinstance(watch.get("id"), str)
            or not watch["id"] or not _counter(watch.get("events")) or not _counter(watch.get("parent_events"))
            or not _limit_hits(watch.get("initial_hits"))):
        raise CgroupError("Invalid v1 OOM notification evidence")


def violation(sample, baseline=None, *, include_kills):
    """Formula checks the container lifetime. Bimetric supplies a verifier baseline."""
    _validate(sample)
    hits = sample["limit_hits"]
    old_hits = [0, None if hits[1] is None else 0]
    old_kills = 0
    old_watch = None
    if baseline is not None:
        _validate(baseline)
        old_hits, old_kills, old_watch = baseline["limit_hits"], baseline["oom_kill"], baseline["observer"]
    if (sample["oom_kill"] < old_kills
            or any((a is None) != (b is None) or (a is not None and a < b) for a, b in zip(hits, old_hits))):
        raise CgroupError("Reset v1 memory counters")
    if include_kills and sample["oom_kill"] > old_kills:
        return True
    watch = sample["observer"]
    if watch and (baseline is None or (old_watch and old_watch["id"] == watch["id"])):
        start = old_watch["events"] if old_watch else 0
        if watch["events"] < start or (old_watch and watch["parent_events"] < old_watch["parent_events"]):
            raise CgroupError("Reset v1 OOM notifications")
        # Ancestor OOMs notify descendants too. A plain eventfd cannot
        # attribute a notification if an ancestor was also under pressure.
        if watch["parent_events"] == 0:
            if watch["events"] > start:
                return True
            if old_watch is not None or not any(watch["initial_hits"]):
                return False
    # With stable caps, local memcg OOM first requires a failed RAM or memsw
    # charge. Successful reclaim also increments these counters.
    if hits == old_hits:
        return False
    raise CgroupError("The v1 memory limit was reached, but local OOM could not be distinguished "
                      "from reclaim or ancestor pressure in this measurement")
