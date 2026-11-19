"""Read Linux cgroup counters for the current process and its container.

Canonical source is environments/cgroups/cgroup_resources.py. Task image
contexts contain identical copies so they can be built independently.
"""

from dataclasses import dataclass
from functools import cache
import json
import os
from pathlib import Path
import re


class CgroupError(RuntimeError):
    """The environment cannot establish the task's required resource budget."""


def _read(path):
    try:
        return path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise CgroupError(f"Cannot read cgroup evidence at {path}: {error}") from error


def _integer(value, path, minimum=0):
    try:
        result = int(value)
        if result >= minimum:
            return result
    except ValueError:
        pass
    raise CgroupError(f"Invalid cgroup value in {path}: {value!r}")


def _mount_path(value):
    return Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value))


@cache
def controller(name):
    """Resolve a controller using this process's membership and visible mounts."""
    return resolve_controller(name, Path("/proc/self/cgroup"))


def resolve_controller(name, membership_file):
    """Resolve a process's membership against mounts visible to the reader."""
    memberships = {}
    for line in _read(membership_file).splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3:
            raise CgroupError(f"Invalid cgroup membership: {line!r}")
        _, controllers, location = fields
        for key in controllers.split(","):
            memberships[key] = Path(location)
    # A hybrid host can mount v2 alongside active v1 controllers.
    version = 1 if name in memberships else 2
    member = memberships.get(name if version == 1 else "")
    if member is None or not member.is_absolute() or ".." in member.parts:
        raise CgroupError(f"No visible cgroup membership for the {name} controller")
    candidates = []
    for line in _read(Path("/proc/self/mountinfo")).splitlines():
        before, _, after = line.partition(" - ")
        mount, filesystem = before.split(), after.split()
        if len(mount) < 6 or len(filesystem) < 3:
            continue
        if version == 1:
            if filesystem[0] != "cgroup" or name not in filesystem[2].split(","):
                continue
        elif filesystem[0] != "cgroup2":
            continue
        root, target = map(_mount_path, mount[3:5])
        if root.is_absolute() and ".." not in root.parts and member.is_relative_to(root):
            candidates.append((len(root.parts), target / member.relative_to(root)))
    if not candidates:
        raise CgroupError(f"No cgroup v{version} mount covers {name} membership {member}")
    _, directory = max(candidates)
    return Controller(version, directory)


@dataclass(frozen=True)
class Controller:
    version: int
    path: Path

    def _text(self, name):
        return _read(self.path / name)

    def _number(self, name, minimum=0):
        return _integer(self._text(name).strip(), self.path / name, minimum)

    def cpu_quota(self):
        """Return (quota in microseconds or None for unlimited, period in microseconds)."""
        if self.version == 1:
            quota = self._number("cpu.cfs_quota_us", -1)
            period = self._number("cpu.cfs_period_us", 1)
            if quota == 0:
                raise CgroupError(f"Invalid zero CPU quota in {self.path / 'cpu.cfs_quota_us'}")
            return (None if quota == -1 else quota), period
        path = self.path / "cpu.max"
        fields = _read(path).split()
        if len(fields) != 2:
            raise CgroupError(f"Expected quota and period in {path}")
        quota, period = fields
        return (None if quota == "max" else _integer(quota, path, 1)), _integer(period, path, 1)

    def memory_limit(self):
        if self.version == 2:
            value = self._text("memory.max").strip()
            return None if value == "max" else _integer(value, self.path / "memory.max", 1)
        # memory.stat includes the tightest ancestor even in a private cgroup namespace.
        path = self.path / "memory.stat"
        bounds = {}
        for line in _read(path).splitlines():
            fields = line.split()
            if fields and fields[0] in ("hierarchical_memory_limit", "hierarchical_memsw_limit"):
                if len(fields) != 2 or fields[0] in bounds:
                    raise CgroupError(f"Malformed {fields[0]} in {path}")
                bounds[fields[0]] = _integer(fields[1], path)
        if "hierarchical_memory_limit" not in bounds:
            raise CgroupError(f"Missing hierarchical_memory_limit in {path}")
        if "hierarchical_memsw_limit" not in bounds and (self.path / "memory.memsw.limit_in_bytes").exists():
            raise CgroupError(f"Missing hierarchical_memsw_limit in {path}")
        limit = min(self._number("memory.limit_in_bytes"), *bounds.values())
        # v1 uses page-rounded LONG_MAX to represent an unbounded limit.
        page_size = os.sysconf("SC_PAGE_SIZE")
        unlimited = (2**63 - 1) // page_size * page_size
        return None if limit >= unlimited else limit

    def swap_limit(self):
        """Return a proven swap-only byte limit, or None when v2 allows 'max'."""
        if self.version == 2:
            name = "memory.swap.max"
            value = self._text(name).strip()
            return None if value == "max" else _integer(value, self.path / name)
        # The v1 combined RAM+swap limit does not prove zero swapped pages.
        # Linux cannot swap when the host has no active swap devices or files.
        swaps = _read(Path("/proc/swaps")).splitlines()
        if swaps and swaps[0].split() == ["Filename", "Type", "Size", "Used", "Priority"] and not any(
                line.strip() for line in swaps[1:]):
            return 0
        raise CgroupError("cgroup v1 cannot verify zero swap with active or unreadable host swap")

    def memory_charge(self):
        name = "memory.usage_in_bytes" if self.version == 1 else "memory.current"
        return self._number(name)

    def memory_peak(self):
        """Peak is a report-only kernel counter."""
        name = "memory.max_usage_in_bytes" if self.version == 1 else "memory.peak"
        try:
            return self._number(name)
        except CgroupError:
            return None

    def cpu_stat(self):
        return self._text("cpu.stat")

    @cache
    def _require_v1_leaf(self):
        # A v1 counter can be local. A leaf has the same process scope as
        # the hierarchical v2 counter, including forked submission processes.
        try:
            if any(path.is_dir() for path in self.path.iterdir()):
                raise CgroupError(f"Cannot establish container-wide v1 OOM counts in {self.path} with child cgroups")
        except OSError as error:
            raise CgroupError(f"Cannot inspect the v1 memory cgroup {self.path}: {error}") from error

    def v1_limit_hits(self):
        # v1 may reject a combined memory+swap charge before charging RAM.
        # Kernels without swap accounting omit the memsw counter entirely.
        try:
            combined = (self.path / "memory.memsw.failcnt").read_text(encoding="ascii")
        except FileNotFoundError:
            combined = None
        except (OSError, UnicodeError) as error:
            raise CgroupError(f"Cannot read memory.memsw.failcnt: {error}") from error
        return [self._number("memory.failcnt"),
                None if combined is None else _integer(combined.strip(), self.path / "memory.memsw.failcnt")]

    def memory_events(self, *required):
        name = "memory.oom_control" if self.version == 1 else "memory.events"
        if self.version == 1:
            if "oom" in required:
                raise CgroupError(f"{self.path / name} does not expose a cumulative oom event count")
            self._require_v1_leaf()
        raw = self._text(name)
        counters = {}
        for line in raw.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] in counters:
                raise CgroupError(f"Malformed cgroup events in {self.path / name}")
            key, value = fields
            counters[key] = _integer(value, self.path / name)
        for key in required:
            if key not in counters:
                raise CgroupError(f"Missing {key} counter in {self.path / name}")
        return raw, counters


def write_resource_error(directory, error):
    """Record why a verifier could not measure a resource-constrained task."""
    path = Path(directory) / "cgroup-status.json"
    path.write_text(json.dumps({"measurement_valid": False, "failure_kind": "cgroup_environment",
                                "error": str(error)}) + "\n")
