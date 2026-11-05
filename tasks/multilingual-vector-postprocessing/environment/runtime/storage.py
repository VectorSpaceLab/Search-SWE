"""Logical task-storage accounting for disk-backed workspaces."""
import os
from pathlib import Path
import stat
import time


STORAGE_LIMIT_BYTES = 100 * 1024**3
INPUT_ROOTS = ("/task/data", "/private/data")
WORK_ROOTS = ("/app", "/tmp", "/var/tmp", "/root", "/dev/shm")
# Framework state is not a permitted place for submission caches or weights.
FRAMEWORK_PATHS = frozenset(("/root/.cache/harbor-rewardkit", "/root/.codex",
                             "/root/.claude", "/root/.pi",
                             "/var/tmp/submission-freeze-status.json"))


def logical_bytes(roots, excluded=FRAMEWORK_PATHS):
    total = 0
    for root in roots:
        root = Path(root)
        if root.is_symlink():
            continue
        for parent, directories, files in os.walk(root):
            directories[:] = [name for name in directories
                              if str(Path(parent) / name) not in excluded]
            for name in files:
                path = Path(parent) / name
                if str(path) in excluded:
                    continue
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue  # A temporary file was removed during sampling.
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
    return total


class StorageBudget:
    def __init__(self, input_roots=INPUT_ROOTS, work_roots=WORK_ROOTS,
                 limit=STORAGE_LIMIT_BYTES):
        self.fixed_bytes = logical_bytes(input_roots)
        self.work_roots = work_roots
        self.limit = limit
        self.peak_bytes = 0
        self.last_check = None

    def check(self, *, force=False):
        now = time.monotonic()
        if force or self.last_check is None or now - self.last_check >= 1:
            self.last_check = now
            used = self.fixed_bytes + logical_bytes(self.work_roots)
            self.peak_bytes = max(self.peak_bytes, used)
        if self.peak_bytes > self.limit:
            raise RuntimeError("100 GiB total task storage exceeded")
        return self.peak_bytes
