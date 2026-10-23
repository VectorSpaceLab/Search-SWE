"""Logical-byte accounting for named, open-unlinked and mapped task files."""
import os
from pathlib import Path
import stat
import time

UID = 10001


class StorageInspectionError(RuntimeError):
    pass


def require_inspection_capabilities():
    fields = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines()
                  if ':' in line)
    effective = int(fields['CapEff'].strip(), 16)
    required = (1 << 19) | (1 << 40)  # SYS_PTRACE and CHECKPOINT_RESTORE
    if effective & required != required:
        raise StorageInspectionError('Verifier needs SYS_PTRACE and CHECKPOINT_RESTORE for storage inspection')


def record(files, info):
    if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        key = (info.st_dev, info.st_ino)
        files[key] = max(files.get(key, 0), info.st_size)


def inventory(roots, *, files=None, deadline=None):
    files = {} if files is None else files

    def inspect(path):
        if deadline is not None and time.monotonic() > deadline:
            raise StorageInspectionError('Task storage inspection timed out')
        try:
            record(files, path.lstat())
        except FileNotFoundError:
            pass

    def failed(error):
        raise StorageInspectionError('Cannot inspect task storage tree') from error

    for root in roots:
        root = Path(root)
        inspect(root)
        if root.is_dir() and not root.is_symlink():
            for base, directories, names in os.walk(root, followlinks=False, onerror=failed):
                for name in directories + names:
                    inspect(Path(base) / name)
    return files


def process_identity(path):
    fields = dict(line.split(':', 1) for line in (path/'status').read_text().splitlines()
                  if ':' in line)
    uid = int(fields['Uid'].split()[0])
    # starttime disambiguates PID reuse during an inspection.
    birth = (path/'stat').read_text().rsplit(') ', 1)[1].split()[19]
    return uid, birth


def total_bytes(roots, fixed_files, *, uid=UID, proc=Path('/proc'), timeout=5):
    """Count each inode once, including files kept alive by preparation services.

    Fixed assets seed the inode map so open handles do not double-charge them.
    Image/system files are excluded: candidate-created regular files are charged
    by inode ownership, independently of their name or deletion status.
    """
    deadline = time.monotonic() + timeout
    files = inventory(roots, files=dict(fixed_files), deadline=deadline)

    def check_deadline():
        if time.monotonic() > deadline:
            raise StorageInspectionError('Task storage inspection timed out')

    def inspect_reference(path):
        check_deadline()
        try:
            info = path.stat()
        except FileNotFoundError:
            return  # The descriptor/mapping was released while being inspected.
        if stat.S_ISREG(info.st_mode) and (info.st_uid == uid or (info.st_dev, info.st_ino) in files):
            record(files, info)

    for process in proc.iterdir():
        if not process.name.isdecimal():
            continue
        check_deadline()
        try:
            identity = process_identity(process)
            if identity[0] != uid:
                continue
            for descriptor in (process/'fd').iterdir():
                inspect_reference(descriptor)
            # A file can survive unlink AND close when mmap still references it.
            # Read maps first to avoid a stat per segment of already-counted files.
            for line in (process/'maps').read_text().splitlines():
                check_deadline()
                fields = line.split(None, 5)
                if len(fields) < 5:
                    raise StorageInspectionError('Malformed process mappings')
                inode = int(fields[4])
                if inode == 0:
                    continue
                major, minor = (int(part, 16) for part in fields[3].split(':'))
                key = (os.makedev(major, minor), inode)
                if key not in files:
                    inspect_reference(process/'map_files'/fields[0])
            if process_identity(process) != identity:
                raise StorageInspectionError('Process identity changed during storage inspection')
        except (FileNotFoundError, ProcessLookupError):
            # A vanished process cannot keep its own descriptors/mappings alive.
            # Remaining services are independently scanned by UID.
            if process.exists():
                raise StorageInspectionError('Process storage evidence disappeared before it could be inspected')
        except (OSError, ValueError, KeyError, IndexError) as error:
            raise StorageInspectionError('Cannot inspect submitted process storage') from error
    return sum(files.values())
