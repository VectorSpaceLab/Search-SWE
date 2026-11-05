"""Retain diagnostic audit traces without copying model credentials."""

import os
from pathlib import Path

source = Path("/audit/output")
target = Path("/logs/verifier/judge-native")
target.mkdir(mode=0o700, exist_ok=True)
secrets = sorted(
    {
        v
        for k, v in os.environ.items()
        if any(x in k.upper() for x in ["KEY", "TOKEN", "PASSWORD", "SECRET"])
        and len(v) > 6
    },
    key=len,
    reverse=True,
)
used = 0
limit = 64 * 1024**2
for p in sorted(source.rglob("*")):
    if (
        p.is_symlink()
        or not p.is_file()
        or p.suffix not in [".jsonl", ".json", ".log", ".txt"]
    ):
        continue
    size = p.stat().st_size
    if used + size > limit:
        continue
    used += size
    try:
        text = p.read_text()
    except UnicodeError:
        continue
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    out = target / p.relative_to(source)
    out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.write_text(text)
    out.chmod(0o600)
