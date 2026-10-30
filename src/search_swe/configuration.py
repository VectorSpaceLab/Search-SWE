"""Literal dotenv configuration; keys never appear in command-line arguments."""

from dataclasses import asdict, dataclass
import io
import os
from pathlib import Path
import subprocess
import tempfile

from dotenv.parser import parse_stream


DEFAULTS = {"AGENT_MODEL": "openai/gpt-6-luna", "SEARCH_SWE_AGENT": "codex",
            "SEARCH_SWE_PROVIDER": "openrouter", "AGENT_REASONING_EFFORT": "max",
            "VERIFIER_OPENAI_BASE_URL": "https://openrouter.ai/api/v1"}
PI_KEYS = {"deepseek/deepseek-flash": "DEEPSEEK_API_KEY", "zai/glm-5.3-flash": "ZAI_API_KEY"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def bindings(path):
    if path.is_symlink():
        raise ValueError("The environment file must be a regular file, not a symlink")
    text = path.read_text() if path.exists() else ""
    result = list(parse_stream(io.StringIO(text)))
    if any(item.error for item in result):
        raise ValueError("Invalid dotenv syntax; fix the environment file before configuring a run")
    return result


def read_env(path):
    return {item.key: item.value for item in bindings(path) if item.key and item.value is not None}


def save_env(path, updates):
    """Replace selected bindings atomically, preserving unrelated text."""
    if path.name == ".env.example":
        raise ValueError("Save credentials to a private .env file; .env.example is the public template")
    original = bindings(path)
    pending = dict(updates)
    output = []
    def assignment(key, value):
        if "\0" in value:
            raise ValueError("Configuration values cannot contain NUL bytes")
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"{key}='{escaped}'\n"
    for item in original:
        if item.key in updates:
            if item.key in pending:
                output.append(assignment(item.key, pending.pop(item.key)))
        else:
            output.append(item.original.string)
    if output and not output[-1].endswith("\n"):
        output.append("\n")
    output.extend(assignment(key, value) for key, value in pending.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".env.tmp-", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write("".join(output))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_config_destination(root, path):
    if path.is_relative_to(root) and (root / ".git").exists():
        relative = str(path.relative_to(root))
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if tracked or not ignored:
            raise ValueError("Save credentials to a Git-ignored environment file, such as the checkout .env")


@dataclass(frozen=True)
class Setting:
    agent: str = "codex"
    provider: str = "openrouter"
    model: str = "openai/gpt-6-luna"
    effort: str = "max"

    def values(self):
        values = {"SEARCH_SWE_AGENT": self.agent, "SEARCH_SWE_PROVIDER": self.provider,
                  "AGENT_MODEL": self.model}
        values["PI_THINKING" if self.agent == "pi" else "AGENT_REASONING_EFFORT"] = self.effort
        return values

    def flags(self):
        args = ["--agent", self.agent, "--model", self.model]
        if self.provider == "openrouter":
            args.append("--openrouter")
        if self.effort:
            args.extend(["--thinking" if self.agent == "pi" else "--reasoning-effort", self.effort])
        return args

    def required(self):
        if self.provider == "openrouter":
            return {"AGENT_OPENROUTER_API_KEY"}
        if self.agent == "codex":
            return {"AGENT_OPENAI_API_KEY", "AGENT_OPENAI_BASE_URL"}
        if self.agent == "claude-code":
            return {"AGENT_ANTHROPIC_API_KEY"}
        if self.model not in PI_KEYS:
            raise ValueError("Pi direct models: " + ", ".join(PI_KEYS))
        return {PI_KEYS[self.model]}

    def validate(self):
        if self.agent not in ("codex", "claude-code", "pi") or self.provider not in ("openrouter", "direct"):
            raise ValueError("Unsupported harness/provider")
        if self.agent == "pi" and self.provider != "direct":
            raise ValueError("Pi currently uses the supported direct-provider adapters")
        if self.provider == "openrouter":
            if "/" not in self.model:
                raise ValueError("OpenRouter requires a complete provider/model slug")
            if self.agent == "claude-code" and not self.model.startswith("anthropic/"):
                raise ValueError("Claude Code on OpenRouter requires an anthropic/ model")
        levels = ["default", "off", "minimal", *EFFORTS] if self.agent == "pi" else ["default", *EFFORTS]
        if self.effort and self.effort not in levels:
            raise ValueError("Unsupported reasoning/thinking level: " + self.effort)
        self.required()
        return self

    def public(self):
        return asdict(self)
