"""Host-owned lifetime locks and recoverable private instance directories."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


LABEL = "searchswe.egress.instance"


def owner_root():
    root = Path(tempfile.gettempdir()) / f"searchswe-egress-owner-{os.getuid()}"
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Unsafe restricted-egress ownership directory")
    return root


class ProjectLock:
    def __init__(self, project):
        self.fd = None
        name = "lock-" + hashlib.sha256(project.encode()).hexdigest()
        fd = os.open(owner_root() / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("Unsafe egress project lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        # Never unlink a lock file: another owner may already hold its inode.


class PrivateDirectory:
    """No GC cleanup: after host failure, preserve its orphan recovery manifest."""

    def __init__(self, instance, project, image, *, daemon_id=None):
        self.name = tempfile.mkdtemp(prefix="instance-" + instance + "-", dir=owner_root())
        self.manifest = {"version": 1, "instance": instance, "project": project,
                         "image": image, "private_directory": self.name, "daemon_id": daemon_id}
        path = Path(self.name) / "owner.json"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(self.manifest, stream)

    def cleanup(self):
        root = Path(self.name)
        if read_manifest(root) != self.manifest:
            raise RuntimeError("Private instance ownership changed; refusing removal")
        shutil.rmtree(root)


def read_manifest(directory):
    directory = Path(directory)
    if directory.parent != owner_root() or not directory.name.startswith("instance-"):
        raise ValueError("Not a managed egress instance directory")
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Unsafe private instance directory")
    fd = os.open(directory / "owner.json", os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Unsafe instance manifest")
        data = json.load(stream)
    if data.get("version") != 1 or data.get("private_directory") != str(directory):
        raise ValueError("Instance manifest mismatch")
    return data
