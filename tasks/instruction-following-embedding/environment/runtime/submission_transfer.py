"""Snapshot a live tmpfs submission; safely restore it in the separate verifier."""
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import tarfile
import tempfile
import time

ARCHIVE = '/var/tmp/search-swe-submission.tar'
SUBMISSION = '/app/submission'
WORKSPACE_BYTES = 28 << 30


def freeze_agent_processes():
    """Quiesce the private agent container before copying its final artifact.

    The collector and its ancestors must remain live for Docker exec. Stopped
    processes are never resumed; Harbor removes the agent container afterwards.
    This is deliberately unavailable to host-side pack/restore callers.
    """
    import psutil

    if (Path(__file__).resolve() != Path('/task/runtime/submission_transfer.py')
            or not Path('/.dockerenv').is_file()
            or psutil.Process(1).name() not in ('sh', 'bash', 'sleep')):
        raise RuntimeError('Process freezing requires the private task container')
    keep = {1, os.getpid(), *(p.pid for p in psutil.Process().parents())}
    deadline = time.monotonic() + 5
    # Repeat after stopping to catch children forked during the first scan.
    stable = 0
    while stable < 2:
        changed = False
        for process in psutil.process_iter():
            if process.pid in keep:
                continue
            try:
                state = process.status()
                if state not in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE,
                                 psutil.STATUS_DEAD):
                    process.send_signal(signal.SIGSTOP)
                    changed = True
            except psutil.NoSuchProcess:
                continue
        stable = 0 if changed else stable + 1
        if time.monotonic() >= deadline:
            raise RuntimeError('Agent processes did not quiesce before collection')
        time.sleep(.02)


def pack(source=SUBMISSION, archive=ARCHIVE):
    source, archive = Path(source), Path(archive)
    archive.unlink(missing_ok=True)
    if not stat.S_ISDIR(source.lstat().st_mode):
        raise ValueError('submission root must be a real directory')
    total = 0
    def regular_only(member):
        nonlocal total
        if not (member.isdir() or member.isfile() or member.islnk()):
            raise ValueError('submission cannot contain symlinks or special files')
        if member.isfile():
            total += member.size
            if total > WORKSPACE_BYTES:
                raise ValueError('submission exceeds the 28 GiB workspace')
        return member
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=archive.parent, delete=False) as stream:
            temporary = Path(stream.name)
            with tarfile.open(fileobj=stream, mode='w') as tf:
                tf.add(source, arcname='.', filter=regular_only)
        os.replace(temporary, archive)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe submission archive path')
    return str(path)


def restore(archive=ARCHIVE, destination=SUBMISSION):
    archive, destination = Path(archive), Path(destination)
    if not stat.S_ISREG(archive.lstat().st_mode):
        raise ValueError('submission archive must be a regular file')
    if destination.exists() or destination.is_symlink():
        raise ValueError('submission restore requires a fresh directory')
    with tarfile.open(archive, mode='r:') as tf:
        members = tf.getmembers()
        indexed = {}
        for member in members:
            name = _relative(member.name)
            if name in indexed:
                raise ValueError('duplicate submission archive path')
            if not (member.isdir() or member.isfile() or member.islnk()):
                raise ValueError('submission archive contains a link or special file')
            indexed[name] = member
        if sum(m.size for m in members if m.isfile()) > WORKSPACE_BYTES:
            raise ValueError('submission exceeds the 28 GiB workspace')
        for member in members:
            if member.islnk():
                target = indexed.get(_relative(member.linkname))
                if target is None or not target.isfile():
                    raise ValueError('unsafe submission archive hard link')
        destination.mkdir(mode=0o700)
        tf.extractall(destination, members=members, filter='data')
    archive.unlink()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze-agent-processes', action='store_true')
    args = parser.parse_args()
    if args.freeze_agent_processes:
        freeze_agent_processes()
    pack()
