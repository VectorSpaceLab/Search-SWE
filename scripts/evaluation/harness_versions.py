"""Harness defaults read from the shared data-only registry."""

from pathlib import Path
import tomllib

_REGISTRY = tomllib.loads((Path(__file__).resolve().parents[2] / "src/search_swe/data/harnesses.toml").read_text())
CODEX_VERSION = _REGISTRY["agents"]["codex"]["version"]
CLAUDE_CODE_VERSION = _REGISTRY["agents"]["claude-code"]["version"]
PI_VERSION = _REGISTRY["agents"]["pi"]["version"]
PI_THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
