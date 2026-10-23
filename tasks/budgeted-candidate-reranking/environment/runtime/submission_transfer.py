"""Snapshot a live tmpfs submission; safely restore it in the separate verifier."""
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile

ARCHIVE = '/tmp/search-swe-submission.tar'
SUBMISSION = '/app/submission'
WORKSPACE_BYTES = 24 << 30


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
                raise ValueError('submission exceeds the 24 GiB workspace')
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
            raise ValueError('submission exceeds the 24 GiB workspace')
        for member in members:
            if member.islnk():
                target = indexed.get(_relative(member.linkname))
                if target is None or not target.isfile():
                    raise ValueError('unsafe submission archive hard link')
        destination.mkdir(mode=0o700)
        tf.extractall(destination, members=members, filter='data')
    archive.unlink()


if __name__ == '__main__':
    pack()
