"""Collect current Antigravity sessions without depending on mtime precision.

The standard-library helper also runs inside task containers via ``python -c``.
Harbor remains responsible for converting the collected native events to ATIF.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import sys
import uuid


OUTPUTS = ("antigravity-cli.trajectory.jsonl", "antigravity-cli.trajectory.json",
           "antigravity-conversation.db", "antigravity-conversation.db-wal",
           "antigravity-conversation.db-shm")


def candidates(home):
    brain = home / ".gemini/antigravity-cli/brain"
    legacy = home / ".agy/antigravity-cli/tmp"
    conversations = home / ".gemini/antigravity-cli/conversations"
    yield from brain.rglob("transcript_full.jsonl")
    for path in legacy.rglob("session-*"):
        if path.suffix in (".json", ".jsonl"):
            yield path
    for path in conversations.rglob("*.db"):
        yield path
        for suffix in ("-wal", "-shm"):
            yield Path(str(path) + suffix)


def fingerprint(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            return None
        return [info.st_dev, info.st_ino, info.st_size,
                hashlib.file_digest(stream, "sha256").hexdigest()]


def capture(home, logs, manifest):
    before = {str(path): value for path in candidates(home)
              if (value := fingerprint(path)) is not None}
    manifest.write_text(json.dumps(before))
    manifest.chmod(0o600)
    # A retained environment must not reuse a previous run's collected output.
    for name in OUTPUTS:
        (logs / name).unlink(missing_ok=True)


def collect(home, logs, manifest):
    before = json.loads(manifest.read_text())
    changed = []
    for path in candidates(home):
        value = fingerprint(path)
        if value is not None and value != before.get(str(path)):
            changed.append(path)
    transcripts = [path for path in changed if path.name == "transcript_full.jsonl"]
    legacy = [path for path in changed if path.name.startswith("session-")]
    if transcripts or legacy:
        source = max(transcripts or legacy, key=lambda path: (path.stat().st_mtime_ns, str(path)))
        shutil.copyfile(source, logs / ("antigravity-cli.trajectory" + source.suffix))
    databases = {Path(str(path).removesuffix("-wal").removesuffix("-shm"))
                 for path in changed if path.name.endswith((".db", ".db-wal", ".db-shm"))}
    if databases:
        source = max(databases, key=lambda path: (path.stat().st_mtime_ns, str(path)))
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(source) + suffix)
            if fingerprint(path) is not None:
                shutil.copyfile(path, logs / ("antigravity-conversation.db" + suffix))
    manifest.unlink()


class AntigravityTrajectory:
    async def run(self, instruction, environment, context):
        self._search_swe_agy_manifest = "/tmp/.search-swe-antigravity-" + uuid.uuid4().hex + ".json"
        result = await self.exec_as_agent(environment, command=self._collection_command("capture"))
        if result.return_code:
            raise RuntimeError("Cannot snapshot Antigravity sessions: " + (result.stderr or result.stdout or "command failed"))
        return await super().run(instruction, environment, context)

    def _collection_command(self, mode):
        source = Path(__file__).read_text()
        return "/opt/conda/bin/python -c " + shlex.quote(source) + " " + mode + " " + shlex.quote(self._search_swe_agy_manifest)

    def _build_collect_trajectory_command(self, scoped):
        # Selection uses the pre-run contents/inodes, including updates to an
        # existing session or SQLite WAL within one filesystem timestamp tick.
        return self._collection_command("collect")


if __name__ == "__main__":
    {"capture": capture, "collect": collect}[sys.argv[1]](
        Path.home(), Path("/logs/agent"), Path(sys.argv[2]))
