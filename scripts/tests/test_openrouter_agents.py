"""OpenRouter compatibility checks for Harbor's pinned CLI adapters."""

import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from harbor.agents.installed.codex import Codex
from scripts.harbor_agents import (
    PreinstalledOpenRouterClaudeCode,
    PreinstalledOpenRouterCodex,
)


CONFIG = Path(__file__).resolve().parents[1] / "openrouter_codex.toml"


class OpenRouterAgents(unittest.TestCase):
    def test_codex_provider_config_and_full_model_slug(self):
        agent = PreinstalledOpenRouterCodex(
            logs_dir=Path("/tmp"), model_name="openai/gpt-6-astra", config=CONFIG
        )
        config = agent._build_effective_config()
        self.assertEqual(config["model_provider"], "openrouter")
        provider = config["model_providers"]["openrouter"]
        self.assertEqual(provider["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(provider["auth"]["command"], "sh")
        self.assertIn("OPENAI_API_KEY", provider["auth"]["args"][-1])

        with patch.object(Codex, "exec_as_agent", new_callable=AsyncMock) as execute:
            asyncio.run(agent.exec_as_agent(
                object(),
                "codex exec --model gpt-6-astra --json -- task",
                env={"OPENAI_API_KEY": "fixture"},
            ))
        self.assertIn("--model openai/gpt-6-astra --json", execute.call_args.args[1])

    def test_codex_fails_if_harbor_command_shape_changes(self):
        agent = PreinstalledOpenRouterCodex(
            logs_dir=Path("/tmp"), model_name="openai/gpt-6-astra", config=CONFIG
        )
        with self.assertRaisesRegex(RuntimeError, "command format changed"):
            asyncio.run(agent.exec_as_agent(object(), "codex exec --model changed --json"))

    def test_claude_uses_bearer_token_and_complete_model(self):
        agent = PreinstalledOpenRouterClaudeCode(
            logs_dir=Path("/tmp"), model_name="anthropic/claude-opus-5.5",
            extra_env={
                "ANTHROPIC_AUTH_TOKEN": "fixture-openrouter-agent-key",
                "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
            },
        )
        self.assertEqual(agent._resolved_model_name(), "anthropic/claude-opus-5.5")
        auth = agent._resolve_auth_env()
        self.assertEqual(auth["ANTHROPIC_AUTH_TOKEN"], "fixture-openrouter-agent-key")
        self.assertEqual(auth["ANTHROPIC_API_KEY"], "")
        self.assertEqual(auth["ANTHROPIC_BASE_URL"], "https://openrouter.ai/api")


if __name__ == "__main__":
    unittest.main()
