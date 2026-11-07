"""Quota-backed agent logs with Harbor's download/convert/upload lifecycle."""

import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import tempfile

import yaml


LOG_MOUNTS = {"/logs/agent", "/logs/verifier", "/logs/artifacts"}
MAX_LOG_ARCHIVE_BYTES = 512 << 20


def check_log_budget(source):
    """Charge the expanded size of each path before host archival writes."""
    source = Path(source)
    total = 0
    pending = [source]
    while pending:
        for entry in pending.pop().iterdir():
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(entry)
                total += 4096
            elif stat.S_ISREG(info.st_mode):
                size = max(info.st_size, info.st_blocks * 512)
                total += ((size + 4095) // 4096) * 4096 + 4096
            else:
                continue
            total += len(os.fsencode(entry.relative_to(source)))
            if total > MAX_LOG_ARCHIVE_BYTES:
                raise RuntimeError("Agent log archive exceeds the 512 MiB diagnostic reserve")
    return total


def configuration(environment_dir):
    source = Path(environment_dir) / "docker-compose.yaml"
    if not source.is_file():
        return None
    extension = (yaml.safe_load(source.read_text()) or {}).get("x-search-swe", {})
    if not isinstance(extension, dict):
        raise ValueError("x-search-swe must be an object")
    value = extension.get("bounded_agent_logs")
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {"finalize"}
            or not isinstance(value["finalize"], list) or not value["finalize"]
            or any(not isinstance(item, str) or not item or "\0" in item for item in value["finalize"])
            or not value["finalize"][0].startswith("/")):
        raise ValueError("bounded_agent_logs requires an absolute finalize command as an argv list")
    return value


def merge_logs(source, destination, *, checked=False):
    """Copy regular log files while preserving trusted host-side metadata."""
    source, destination = Path(source), Path(destination)
    if not checked:
        check_log_budget(source)
    if destination.is_symlink():
        raise ValueError("Agent log destination must be a real directory")
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            if not target.exists():
                target.mkdir(mode=0o700)
            if target.is_dir() and not target.is_symlink():
                merge_logs(entry, target, checked=True)
        elif stat.S_ISREG(mode) and not target.exists() and not target.is_symlink():
            with entry.open("rb") as incoming, target.open("xb") as outgoing:
                os.fchmod(outgoing.fileno(), 0o600)
                shutil.copyfileobj(incoming, outgoing)


class BoundedLogs:
    def __init__(self, *args, **kwargs):
        environment_dir = kwargs.get("environment_dir") or (args[0] if args else None)
        self._bounded_agent_logs = configuration(environment_dir) if environment_dir is not None else None
        self._bounded_logs_finalized = False
        self._bounded_logs_error = None
        super().__init__(*args, **kwargs)
        if self._bounded_agent_logs:
            # The task links /logs/agent into its quota-backed filesystem.
            # Host logs are populated through Harbor's non-mounted lifecycle.
            self._mounts = [mount for mount in self._mounts if mount.get("target") not in LOG_MOUNTS]

    @property
    def capabilities(self):
        original = super().capabilities
        return original.model_copy(update={"mounted": False}) if self._bounded_agent_logs else original

    async def finalize_agent_logs(self):
        if not self._bounded_agent_logs:
            return
        if self._bounded_logs_error:
            raise RuntimeError(self._bounded_logs_error)
        if not self._bounded_logs_finalized:
            result = await self.exec(shlex.join(self._bounded_agent_logs["finalize"]), user="root", timeout_sec=120)
            if result.return_code:
                self._bounded_logs_error = "Could not freeze bounded agent logs: " + (result.stderr or result.stdout or "finalizer failed")
                (self.trial_paths.trial_dir / "bounded-logs-error.txt").write_text(self._bounded_logs_error)
                raise RuntimeError(self._bounded_logs_error)
            self._bounded_logs_finalized = True

    async def download_dir(self, source_dir, target_dir):
        if not self._bounded_agent_logs or PurePosixPath(source_dir) != PurePosixPath("/logs/agent"):
            return await super().download_dir(source_dir, target_dir)
        await self.finalize_agent_logs()
        with tempfile.TemporaryDirectory(prefix=".bounded-logs-", dir=self.trial_paths.trial_dir) as directory:
            await super().download_dir(source_dir, directory)
            merge_logs(directory, target_dir)


class FinalizeBoundedLogs:
    """Fail the agent phase on archival errors before Harbor's best-effort sync."""

    async def run(self, instruction, environment, context):
        self._bounded_logs_enabled = isinstance(getattr(environment, "_bounded_agent_logs", None), dict)
        try:
            return await super().run(instruction, environment, context)
        finally:
            if self._bounded_logs_enabled:
                await environment.finalize_agent_logs()
                # Some native agents generate their host ATIF during run and
                # fill AgentContext, so Harbor skips populate_context_post_run.
                check_log_budget(self.logs_dir)

    def populate_context_post_run(self, context):
        result = super().populate_context_post_run(context)
        if getattr(self, "_bounded_logs_enabled", False):
            # Host conversion can expand raw logs. Check before Harbor uploads
            # the ATIF and starts the independent verifier.
            check_log_budget(self.logs_dir)
        return result
