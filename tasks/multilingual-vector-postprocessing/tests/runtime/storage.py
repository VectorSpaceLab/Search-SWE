"""Logical task-storage accounting for disk-backed workspaces."""
import ctypes
import os
from pathlib import Path
import stat
import time

from isolation import UID


STORAGE_LIMIT_BYTES = 100 * 1024**3
INPUT_ROOTS = ("/task/data", "/private/data")
WORK_ROOTS = ("/app", "/tmp", "/var/tmp", "/root", "/dev/shm")
# Framework state is not a permitted place for submission caches or weights.
FRAMEWORK_PATHS = frozenset(("/root/.cache/harbor-rewardkit", "/root/.codex",
                             "/root/.claude", "/root/.pi",
                             "/var/tmp/submission-freeze-status.json"))


def logical_bytes(roots, excluded=FRAMEWORK_PATHS, *, include_retained=False):
    total = 0
    seen = set()
    roots = tuple(Path(root).absolute() for root in roots)

    def account(path, *, reference=False):
        nonlocal total
        try:
            if reference:
                target = os.readlink(path)
                if not retained_path(target):
                    return
                info = path.stat()
            else:
                info = path.lstat()
        except (FileNotFoundError, ProcessLookupError):
            return  # The file, descriptor or mapping was just released.
        identity = info.st_dev, info.st_ino
        if stat.S_ISREG(info.st_mode) and (not reference or identity not in seen):
            # Preserve named-file accounting; additional FD/mmap references
            # to the same inode must not charge its logical size again.
            total += info.st_size
            seen.add(identity)

    def retained_path(target):
        if target.endswith(' (deleted)'):
            target = target[:-10]
        if any(target == path or target.startswith(path + '/') for path in excluded):
            return False
        return (target.startswith('/memfd:') or
                any(target == str(root) or target.startswith(str(root) + '/') for root in roots))

    def walk_error(error):
        if not isinstance(error, FileNotFoundError):
            raise error

    for root in roots:
        if root.is_symlink() or str(root) in excluded:
            continue
        for parent, directories, files in os.walk(root, onerror=walk_error):
            directories[:] = [name for name in directories
                              if str(Path(parent) / name) not in excluded]
            for name in files:
                path = Path(parent) / name
                if str(path) in excluded:
                    continue
                account(path)
    if include_retained:
        libc = ctypes.CDLL(None)
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                status = (process / 'status').read_text().splitlines()
                uid = int(next(line.split()[1] for line in status if line.startswith('Uid:')))
            except (FileNotFoundError, ProcessLookupError):
                continue
            # Include sandbox workers, escaped descendants of that UID, and
            # same-UID workers used by the public development evaluator.
            if uid not in (UID, os.getuid()):
                continue
            attempt = 0
            exit_deadline = None
            while True:
                # Only this inspecting thread's filesystem IDs change. Real,
                # effective and saved IDs of the supervisor remain untouched.
                previous_gid = libc.setfsgid(uid) if uid != os.geteuid() else None
                previous_uid = libc.setfsuid(uid) if uid != os.geteuid() else None
                denied = False
                try:
                    for descriptor in (process / 'fd').iterdir():
                        account(descriptor, reference=True)
                    for line in (process / 'maps').read_text(errors='surrogateescape').splitlines():
                        fields = line.split(None, 5)
                        if len(fields) < 6 or not retained_path(fields[5]):
                            continue
                        major, minor = (int(part, 16) for part in fields[3].split(':'))
                        identity = os.makedev(major, minor), int(fields[4])
                        if identity not in seen:
                            # stat the backing file, not the mapped address range:
                            # even a partial mapping retains the whole file.
                            account(process / 'map_files' / fields[0], reference=True)
                except (FileNotFoundError, ProcessLookupError):
                    break
                except PermissionError:
                    denied = True
                finally:
                    if previous_uid is not None:
                        libc.setfsuid(previous_uid)
                        libc.setfsgid(previous_gid)
                if not denied:
                    break
                try:
                    fields = (process / 'stat').read_text().rsplit(') ', 1)[1].split()
                except (FileNotFoundError, ProcessLookupError):
                    break
                if fields[0] == 'Z':
                    break
                # An exiting process can briefly deny inspection before its
                # retained files disappear. A live, uninspectable worker fails.
                if int(fields[6]) & 0x00000004:  # PF_EXITING
                    if exit_deadline is None:
                        exit_deadline = time.monotonic() + 1
                    if time.monotonic() < exit_deadline:
                        time.sleep(.005)
                        continue
                if attempt == 0:
                    attempt += 1
                    time.sleep(.005)  # Allow a brief setuid/dumpability transition.
                else:
                    raise RuntimeError('Cannot inspect submission open files or mappings')
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
            used = self.fixed_bytes + logical_bytes(self.work_roots, include_retained=True)
            self.peak_bytes = max(self.peak_bytes, used)
        if self.peak_bytes > self.limit:
            raise RuntimeError("100 GiB total task storage exceeded")
        return self.peak_bytes
