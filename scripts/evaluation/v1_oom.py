"""Expose v1 kernel OOM notifications to trusted graders on read-only cgroup mounts."""

import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import uuid

from environments.cgroups.cgroup_resources import CgroupError, resolve_controller
from environments.cgroups.v1_oom import SOCKET


class OomNotifications:
    def __init__(self, memory):
        self.files = ExitStack()
        info = memory.path.stat()
        self.cgroup = [info.st_dev, info.st_ino]
        self.id = uuid.uuid4().hex
        self.counts = [0, 0]
        try:
            if memory.memory_events("oom_kill_disable")[1]["oom_kill_disable"] != 0:
                raise CgroupError("v1 OOM notifications require the kernel OOM killer")
            parent = memory.path.parent
            # An ancestor's OOM is also announced to its descendants. Register
            # at the parent first to distinguish this from an OOM in the task.
            self.parent_fd = self.register(parent)
            self.fd = self.register(memory.path)
            self.initial_hits = memory.v1_limit_hits()
        except BaseException:
            self.files.close()
            raise

    def register(self, directory):
        fd = os.eventfd(0, os.EFD_CLOEXEC | os.EFD_NONBLOCK)
        self.files.callback(os.close, fd)
        with (directory / "memory.oom_control").open("rb") as control:
            with (directory / "cgroup.event_control").open("wb", buffering=0) as registration:
                registration.write(f"{fd} {control.fileno()}".encode())
        return fd

    def sample(self):
        for i, fd in enumerate((self.fd, self.parent_fd)):
            try:
                self.counts[i] += os.eventfd_read(fd)
            except BlockingIOError:
                pass
        return {"id": self.id, "cgroup": self.cgroup, "events": self.counts[0], "parent_events": self.counts[1],
                "initial_hits": self.initial_hits}


class V1OomObserver:
    """One private endpoint per task phase. The peer cannot select a host path."""
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="search-swe-oom-", dir="/tmp")
        self.memory = self.watch = None
        self.server = None

    async def start(self):
        path = Path(self.directory.name) / Path(SOCKET).name
        self.server = await asyncio.start_unix_server(self.respond, path=path)
        path.chmod(0o600)
        return {"type": "bind", "source": self.directory.name,
                "target": str(Path(SOCKET).parent), "read_only": True}

    def respond(self, _reader, writer):
        sample = None
        try:
            peer = writer.get_extra_info("socket")
            pid, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid == 0 and self.server is not None:
                memory = resolve_controller("memory", Path(f"/proc/{pid}/cgroup"))
                if self.watch is None and memory.version == 1 and memory.memory_limit() is not None:
                    self.watch = OomNotifications(memory)
                    self.memory = memory
                if self.watch is not None and memory == self.memory:
                    sample = self.watch.sample()
        except (OSError, CgroupError):
            pass  # The grader can still prove untouched limits or a Formula OOM kill.
        writer.write(json.dumps(sample).encode() + b"\n")
        writer.close()

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server = None
        if self.watch is not None:
            self.watch.files.close()
        self.directory.cleanup()
