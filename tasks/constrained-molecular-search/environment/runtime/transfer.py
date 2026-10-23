"""Preserve a frozen submission across Harbor's separate-container handoff."""
import argparse
import os
from pathlib import Path, PurePosixPath
import signal
import tarfile
import time

import psutil

ARCHIVE = Path("/var/tmp/molecular-submission.tar")
SUBMISSION = Path("/app/submission")
MAX_BYTES = 64 << 30


def quiesce():
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Collection cleanup is restricted to the task container")
    keep = {1, os.getpid(), *(p.pid for p in psutil.Process().parents())}
    for process in psutil.process_iter(["ppid", "cmdline"]):
        command = process.info["cmdline"] or []
        if process.info["ppid"] == 1 and command and command[-1] == "infinity":
            keep.add(process.pid)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for process in psutil.process_iter():
            try:
                if process.pid not in keep:
                    process.send_signal(sig)
            except psutil.NoSuchProcess:
                pass
        time.sleep(.2)


def pack(source=SUBMISSION, archive=ARCHIVE):
    source, archive = Path(source), Path(archive)
    archive.unlink(missing_ok=True)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Missing regular submission directory")
    for path in source.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Only regular files and directories can be submitted")
    total = 0

    def checked(member):
        nonlocal total
        if not (member.isfile() or member.isdir()):
            raise ValueError("Only regular files and directories can be submitted")
        total += member.size
        if total > MAX_BYTES:
            raise ValueError("Submission exceeds 64 GiB")
        return member

    temporary = archive.with_suffix(".partial")
    try:
        with tarfile.open(temporary, "w", dereference=True) as stream:
            stream.add(source, arcname=".", filter=checked)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)


def restore(archive=ARCHIVE, destination=SUBMISSION):
    archive, destination = Path(archive), Path(destination)
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("Missing regular submission archive")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Submission destination must be fresh")
    with tarfile.open(archive, "r:") as stream:
        members, names, total = stream.getmembers(), set(), 0
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or str(name) in names:
                raise ValueError("Unsafe or duplicate submission path")
            if not (member.isdir() or member.isfile()):
                raise ValueError("Archive links and special files are forbidden")
            names.add(str(name))
            total += member.size
            if total > MAX_BYTES:
                raise ValueError("Submission exceeds 64 GiB")
        destination.mkdir(mode=0o700)
        stream.extractall(destination, members=members, filter="data")
    archive.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.collect:
        quiesce()
    pack()
