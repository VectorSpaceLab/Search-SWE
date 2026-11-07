"""Literal dotenv configuration; keys never appear in command-line arguments."""

from dataclasses import asdict, dataclass
import io
import os
from pathlib import Path
import subprocess
import tempfile

from dotenv.parser import parse_stream
from . import harbor_native, harnesses, pi_models


DEFAULTS = {"AGENT_MODEL": "openai/gpt-6-luna", "SEARCH_SWE_AGENT": "codex",
            "SEARCH_SWE_PROVIDER": "openrouter", "AGENT_REASONING_EFFORT": "max",
            "VERIFIER_OPENAI_BASE_URL": "https://openrouter.ai/api/v1"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def default_model(agent, provider):
    if provider == "native":
        return ""
    if provider == "openrouter":
        return "anthropic/claude-opus-5.5" if agent == "claude-code" else DEFAULTS["AGENT_MODEL"]
    if agent == "pi":
        return "deepseek/deepseek-flash"
    return ""


def saved_setting(values):
    agent = values.get("SEARCH_SWE_AGENT") or "codex"
    provider = values.get("SEARCH_SWE_PROVIDER") or harbor_native.default_route(agent)
    model = values.get("AGENT_MODEL") or default_model(agent, provider)
    effort = values.get("PI_THINKING" if agent == "pi" else "AGENT_REASONING_EFFORT")
    if not effort:
        effort = "max" if (agent, provider, model) == ("codex", "openrouter", DEFAULTS["AGENT_MODEL"]) else "default"
    return Setting(agent, provider, model, effort, values.get("SEARCH_SWE_AGENT_CONFIG") or None,
                   values.get("SEARCH_SWE_AGENT_VERSION") or None)


def resolve_setting(current, args):
    agent = args.agent or current.agent
    provider = args.provider or (current.provider if agent == current.agent else harbor_native.default_route(agent))
    same_route = (agent, provider) == (current.agent, current.provider)
    model = args.model if args.model is not None else (current.model if same_route else default_model(agent, provider))
    effort = args.reasoning_effort or (current.effort if same_route and model == current.model else "default")
    config = getattr(args, "agent_config", None)
    config = str(config) if config is not None else current.agent_config if same_route else None
    version = getattr(args, "agent_version", None)
    version = version if version is not None else current.agent_version if agent == current.agent else None
    return Setting(agent, provider, model, effort, config, version).validate()


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
    agent_config: str | None = None
    agent_version: str | None = None

    def values(self):
        values = {"SEARCH_SWE_AGENT": self.agent, "SEARCH_SWE_PROVIDER": self.provider,
                  "AGENT_MODEL": self.model}
        values["PI_THINKING" if self.agent == "pi" else "AGENT_REASONING_EFFORT"] = self.effort
        values["SEARCH_SWE_AGENT_CONFIG"] = self.agent_config or ""
        values["SEARCH_SWE_AGENT_VERSION"] = self.agent_version or ""
        return values

    def flags(self):
        args = ["--agent", self.agent]
        if self.agent_version:
            args.extend(["--agent-version", self.agent_version])
        if self.model or self.provider == "native":
            args.extend(["--model", self.model])
        if self.provider == "native":
            args.append("--native")
            if self.agent_config:
                args.extend(["--agent-config", self.agent_config])
        if self.provider == "openrouter":
            args.append("--openrouter")
        if self.effort and (self.provider != "native" or self.effort != "default"):
            args.extend(["--thinking" if self.agent == "pi" and self.provider != "native" else "--reasoning-effort", self.effort])
        return args

    def required(self, env=None):
        if self.provider == "native":
            return harbor_native.plan(self.agent, self.model, env or {}, self.agent_config)["required"]
        if self.provider == "openrouter":
            return {"AGENT_OPENROUTER_API_KEY"}
        if self.agent == "codex":
            return {"AGENT_OPENAI_API_KEY", "AGENT_OPENAI_BASE_URL"}
        if self.agent == "claude-code":
            return {"AGENT_ANTHROPIC_API_KEY"}
        return pi_models.required_variables(self.model, env)

    def validate(self):
        harbor_native.require_name(self.agent)
        if self.agent_version:
            harnesses.version_argument(self.agent_version)
        if self.provider not in harbor_native.routes(self.agent):
            raise ValueError("Unsupported harness/provider")
        if ((not self.model and self.provider != "native") or self.model != self.model.strip()
                or any(c.isspace() for c in self.model)):
            raise ValueError("Provide a model ID with --model or choose one in the interactive wizard")
        if self.provider == "openrouter":
            from .model_catalog import MODEL_ID
            if not MODEL_ID.fullmatch(self.model):
                raise ValueError("OpenRouter requires a complete provider/model slug")
        if self.agent_config and self.provider != "native":
            raise ValueError("--agent-config is used with --provider native")
        if self.agent == "pi" and self.provider != "native":
            pi_models.selection(pi_models.native_model(self.model, self.provider))
        levels = ["default", "off", "minimal", *EFFORTS] if self.agent == "pi" else ["default", *EFFORTS]
        if self.effort and self.effort not in levels:
            raise ValueError("Unsupported reasoning/thinking level: " + self.effort)
        if self.provider != "native":
            self.required()
        return self

    def public(self):
        return asdict(self)
