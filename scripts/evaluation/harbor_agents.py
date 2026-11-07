"""Harbor integrations using centrally managed, verified harness installations."""

from harbor.agents.installed.codex import Codex
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.pi import Pi
from harbor.agents.model_connection import ResolvedModelConnection
from dataclasses import replace
import json
import re
import shlex
from pathlib import Path

from scripts.evaluation.pi_trajectory import PiTrajectory
from scripts.evaluation.harness_versions import PI_THINKING_LEVELS
from scripts.evaluation.harness_install import ManagedHarness
from scripts.evaluation.bounded_logs import FinalizeBoundedLogs

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from search_swe import pi_models


class ManagedCodex(FinalizeBoundedLogs, ManagedHarness, Codex):
    HARNESS_NAME = "codex"

    def parse_version(self, stdout: str) -> str:
        # Startup warnings can precede the version. Require one complete CLI
        # version line; a version mentioned inside a warning is not evidence.
        versions = [match.group(1) for line in stdout.splitlines()
                    if (match := re.fullmatch(r"codex-cli ([0-9]+\.[0-9]+\.[0-9]+)", line.strip()))]
        return versions[0] if len(versions) == 1 else ""

class ManagedOpenRouterCodex(ManagedCodex):
    """Keep the full OpenRouter model slug in Harbor's Codex command."""

    async def exec_as_agent(self, environment, command, **kwargs):
        # Harbor 0.22.0 strips the provider prefix in Codex.run(). Replace
        # only its model flag; fail if a future Harbor release changes it.
        if "codex exec " in command:
            flags, separator, instruction = command.partition("-- ")
            bare_model = self.model_name.split("/")[-1]
            old = f"--model {bare_model} --json "
            if not separator or flags.count(old) != 1:
                raise RuntimeError(
                    "Harbor's Codex command format changed; OpenRouter model may be truncated"
                )
            command = (
                flags.replace(old, f"--model {shlex.quote(self.model_name)} --json ", 1)
                + separator + instruction
            )
        return await super().exec_as_agent(environment, command, **kwargs)


class ManagedClaudeCode(FinalizeBoundedLogs, ManagedHarness, ClaudeCode):
    HARNESS_NAME = "claude-code"


class ManagedOpenRouterClaudeCode(ManagedClaudeCode):
    """Use OpenRouter's bearer token with Claude Code's Anthropic endpoint."""

    def _resolve_auth_env(self):
        env = super()._resolve_auth_env()
        token = self._get_env("ANTHROPIC_AUTH_TOKEN")
        if not token or env.get("ANTHROPIC_BASE_URL") != "https://openrouter.ai/api":
            raise RuntimeError(
                "OpenRouter Claude Code requires its bearer token and fixed base URL"
            )
        env["ANTHROPIC_API_KEY"] = ""
        env["ANTHROPIC_AUTH_TOKEN"] = token
        return env


class ManagedPi(FinalizeBoundedLogs, PiTrajectory, ManagedHarness, Pi):
    HARNESS_NAME = "pi"

    CLI_FLAGS = [replace(flag, choices=list(PI_THINKING_LEVELS))
                 if flag.kwarg == "thinking" else flag for flag in Pi.CLI_FLAGS]

    def __init__(self, *args, model_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._model_config = (pi_models.validate_model_config(self.model_name, model_config)
                              if model_config is not None else None)

    @property
    def model_connection(self):
        provider, _, _ = pi_models.selection(self.model_name)
        # Pi owns provider/key resolution. Harbor's generic provider aliases and
        # custom endpoint inference differ from Pi (notably Azure and Copilot).
        return ResolvedModelConnection(provider=provider, api_key=None, base_url=None,
                                       configured_base_url=None, env={**self.extra_env,
                                       "PI_CODING_AGENT_DIR": "/tmp/search-swe-pi", "PI_OFFLINE": "1"})

    def _get_env(self, key, *alternatives):
        if key == "ANTHROPIC_OAUTH_TOKEN":
            return None
        return super()._get_env(key, *alternatives)

    async def exec_as_agent(self, environment, command, **kwargs):
        if "pi --print --mode json " in command:
            provider, model_id, _ = pi_models.selection(self.model_name)
            old = f"--provider {provider} --model {model_id} "
            if command.count(old) != 1:
                raise RuntimeError("Harbor's Pi command format changed; cannot preserve the selected model")
            command = command.replace(old, f"--provider {shlex.quote(provider)} --model {shlex.quote(model_id)} ", 1)
        return await super().exec_as_agent(environment, command, **kwargs)

    async def _prepare_model(self, environment):
        provider, model_id, info = pi_models.selection(self.model_name)
        model = self._model_config
        if provider == "openrouter" and model_id not in info["models"] and model is None:
            raise RuntimeError("New Pi OpenRouter models need preflight metadata; launch through search-swe or scripts/evaluation/run_task.py")
        if model is not None:
            await self.exec_as_agent(environment, "mkdir -p /tmp/search-swe-pi && chmod 700 /tmp/search-swe-pi")
            await self._upload_config_text(environment, content=json.dumps({"providers": {"openrouter": {
                "baseUrl": "https://openrouter.ai/api/v1", "api": "openai-completions", "models": [model]
            }}}), remote_path="/tmp/search-swe-pi/models.json", filename="models.json")

    async def run(self, instruction, environment, context):
        await self._prepare_model(environment)
        await super().run(instruction, environment, context)

# Published run configurations retain these import paths.
PreinstalledCodex = ManagedCodex
PreinstalledOpenRouterCodex = ManagedOpenRouterCodex
PreinstalledClaudeCode = ManagedClaudeCode
PreinstalledOpenRouterClaudeCode = ManagedOpenRouterClaudeCode
PreinstalledPi = ManagedPi
