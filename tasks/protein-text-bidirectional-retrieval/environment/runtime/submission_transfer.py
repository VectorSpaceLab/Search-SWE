"""Snapshot a live tmpfs submission; safely restore it in the separate verifier."""
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile
import signal
import time
import psutil

ARCHIVE = '/var/tmp/search-swe-submission.tar'
SUBMISSION = '/app/submission'
SUBMISSION_BYTES = 256 << 10


def quiesce_agent():
    """Stop task processes in this private container before taking the snapshot."""
    if not Path('/.dockerenv').is_file():
        raise RuntimeError('Collection process cleanup requires the task Docker container')
    keep = {1, os.getpid(), *(p.pid for p in psutil.Process().parents())}
    # Harbor's main service uses `sh -c sleep infinity`; retain its real
    # keepalive child so stopping training does not terminate the container.
    for process in psutil.process_iter(['ppid', 'cmdline']):
        try:
            command = process.info['cmdline'] or []
            if (process.info['ppid'] == 1 and command and command[-1] == 'infinity' and
                    Path(process.exe()).name == 'sleep'):
                keep.add(process.pid)
        except psutil.NoSuchProcess:
            pass
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for process in psutil.process_iter(['status']):
            if process.pid in keep or process.info['status'] == psutil.STATUS_ZOMBIE:
                continue
            try:
                process.send_signal(sig)
            except psutil.NoSuchProcess:
                pass
        time.sleep(.2)
    live = [p.pid for p in psutil.process_iter(['status'])
            if p.pid not in keep and p.info['status'] != psutil.STATUS_ZOMBIE]
    if live:
        raise RuntimeError('Task processes remained alive during submission collection')


def pack(source=SUBMISSION, archive=ARCHIVE):
    source, archive = Path(source), Path(archive)
    archive.unlink(missing_ok=True)
    if not stat.S_ISDIR(source.lstat().st_mode):
        raise ValueError('submission root must be a real directory')
    # Count every path, including hard links, by logical size before tar deduplication.
    total = sum(p.lstat().st_size for p in source.rglob('*') if p.is_file() and not p.is_symlink())
    if total > SUBMISSION_BYTES:
        raise ValueError('submission exceeds 256 KiB total logical bytes')
    def regular_only(member):
        if not (member.isdir() or member.isfile() or member.islnk()):
            raise ValueError('submission cannot contain symlinks or special files')
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
        total = sum(m.size for m in members if m.isfile())
        for member in members:
            if member.islnk():
                target = indexed.get(_relative(member.linkname))
                if target is None or not target.isfile():
                    raise ValueError('unsafe submission archive hard link')
                total += target.size
        if total > SUBMISSION_BYTES:
            raise ValueError('submission exceeds 256 KiB total logical bytes')
        destination.mkdir(mode=0o700)
        tf.extractall(destination, members=members, filter='data')
    archive.unlink()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--collect', action='store_true')
    if parser.parse_args().collect:
        quiesce_agent()
    pack()
