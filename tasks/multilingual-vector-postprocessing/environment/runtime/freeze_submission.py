"""Trusted post-agent collection: stop background work and freeze the artifact."""
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import stat
import tempfile
import time

import psutil


def container_resources():
    """Read cumulative kernel counters once after stopping agent work."""
    result = {"scope": "Agent container cumulative counters after stopping agent work, including setup; artifact transport follows"}
    root = Path("/sys/fs/cgroup")
    for name in ("cpu.max", "memory.max", "memory.swap.max", "pids.max"):
        try:
            result[name] = (root / name).read_text().strip()
        except OSError:
            pass
    for name in ("memory.peak", "pids.peak"):
        try:
            result[name] = int((root / name).read_text())
        except (OSError, ValueError):
            pass
    try:
        result["cpu.stat"] = {key: int(value) for key, value in
                              (line.split() for line in (root / "cpu.stat").read_text().splitlines())}
    except (OSError, ValueError):
        pass
    return result


def main():
    if os.environ.get("SEARCH_SWE_AGENT_CONTAINER") != "1":
        raise RuntimeError("Collection is restricted to this task's disposable agent container")
    current = psutil.Process()
    protected = {1, current.pid, *(p.pid for p in current.parents())}
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for process in psutil.process_iter():
            try:
                if process.pid not in protected:
                    process.send_signal(sig)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(.2)
    deadline = time.monotonic() + 5
    while True:
        remaining = []
        for process in psutil.process_iter():
            try:
                if process.pid not in protected and process.status() != psutil.STATUS_ZOMBIE:
                    remaining.append(process.pid)
            except psutil.NoSuchProcess:
                pass
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(.1)
    root = Path("/app/submission")
    status = {"valid": False, "files": [], "reason": "missing transform.py",
              "container_resources": container_resources()}
    try:
        if remaining:
            raise ValueError("Background work did not stop before artifact freezing")
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Submission root must be a real directory")
        paths = []
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in directories:
                path = Path(parent) / name
                if not stat.S_ISDIR(path.lstat().st_mode):
                    raise ValueError("Linked or non-directory submission entry")
            for name in files:
                path = Path(parent) / name
                mode = path.lstat().st_mode
                if not stat.S_ISREG(mode):
                    raise ValueError("Linked or non-regular submission entry")
                paths.append((path, mode))
        if not (root / "transform.py").is_file():
            raise ValueError("Missing transform.py")
        total = sum(path.stat().st_size for path, mode in paths)
        if total > 100 * 1024**3:
            raise ValueError("Submission exceeds the total storage limit")
        for path, mode in sorted(paths):
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            os.chown(path, 0, 0)
            path.chmod(0o555 if mode & 0o111 else 0o444)
            status["files"].append(dict(path=str(path.relative_to(root)), size_bytes=path.stat().st_size, sha256=digest))
        for parent, directories, files in os.walk(root, topdown=False):
            os.chown(parent, 0, 0)
            Path(parent).chmod(0o555)
        status.update(valid=True, reason=None, submitted_bytes=total)
    except Exception as error:
        status.update(valid=False, reason=str(error), files=[])
        # Still supply a real, harmless artifact to the framework, so a bad
        # submission is a measured zero rather than a collection-path error.
        if root.exists() or root.is_symlink():
            root.rename(Path("/app") / ("rejected-submission-" + str(os.getpid())))
        root.mkdir()
        root.chmod(0o555)
    destination = Path("/var/tmp/submission-freeze-status.json")
    fd, temporary = tempfile.mkstemp(prefix="submission-freeze-", dir=destination.parent)
    with os.fdopen(fd, "w") as handle:
        json.dump(status, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    # Harbor 0.22 downloads with Docker cp, which cannot see this engine's
    # tmpfs contents. Only after all agent work stopped, materialize the frozen
    # artifact in its framework-owned bind mount, never as an agent cache.
    log_root = Path("/logs/agent")
    log_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".collect-submission-", dir=log_root))
    try:
        shutil.copytree(root, stage / "submission")
        published = log_root / "collected-submission"
        if published.is_symlink() or (published.exists() and not published.is_dir()):
            published.unlink()
        elif published.exists():
            shutil.rmtree(published)
        os.replace(stage / "submission", published)
        # Copy the collector's own regular status, never any agent-written file.
        fd, metadata = tempfile.mkstemp(prefix=".collect-status-", dir=log_root)
        with os.fdopen(fd, "w") as handle:
            json.dump(status, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(metadata, log_root / "submission-freeze-status.json")
    finally:
        shutil.rmtree(stage)


if __name__ == "__main__":
    main()
