#!/usr/bin/env python3
"""Run RewardKit 0.2.0 with DeepSeek V4.1 Flash through OpenRouter's Responses API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from rewardkit.agents import CodexBackend, register_agent


MODEL = {
    "slug": "deepseek/deepseek-v4.1-flash",
    "display_name": "DeepSeek V4.1 Flash (OpenRouter)",
    "prefer_websockets": False,
    "support_verbosity": True,
    "default_verbosity": "low",
    "apply_patch_tool_type": "freeform",
    "web_search_tool_type": "text",
    "input_modalities": ["text", "image"],
    "supports_image_detail_original": True,
    "truncation_policy": {"mode": "tokens", "limit": 10000},
    "supports_parallel_tool_calls": True,
    "multi_agent_version": "v2",
    "use_responses_lite": False,
    "context_window": 1048576,
    "max_context_window": 1048576,
    "effective_context_window_percent": 95,
    "comp_hash": "3000",
    "reasoning_summary_format": "experimental",
    "default_reasoning_summary": "none",
    "default_reasoning_level": "high",
    "supported_reasoning_levels": [
        {"effort": "low", "description": "Fast responses with lighter reasoning"},
        {"effort": "high", "description": "Extra reasoning for complex problems"},
    ],
    "shell_type": "shell_command",
    "visibility": "list",
    "minimal_client_version": "0.144.0",
    "supported_in_api": True,
    "priority": 1,
    "experimental_supported_tools": [],
    "supports_search_tool": True,
    "supports_reasoning_summaries": True,
    "base_instructions": (
        "You are a coding agent. Follow the supplied judge instructions and "
        "return the requested structured result."
    ),
}


def deepseek_base_url() -> str:
    value = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        value != "https://openrouter.ai/api/v1"
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "OPENAI_BASE_URL must be https://openrouter.ai/api/v1 for the "
            "OpenRouter trajectory judge"
        )
    return value


def configure_codex_home(codex_home: Path, base_url: str) -> None:
    """Write non-secret DeepSeek settings into RewardKit's temporary home."""
    catalog = codex_home / "models.json"
    catalog.write_text(json.dumps({"models": [MODEL]}), encoding="utf-8")
    catalog.chmod(0o600)

    config = codex_home / "config.toml"
    mcp_config = config.read_text(encoding="utf-8") if config.is_file() else ""
    config.write_text(
        'model_provider = "openrouter"\n'
        'model_reasoning_effort = "high"\n'
        f"model_catalog_json = {json.dumps(str(catalog))}\n\n"
        '[model_providers.openrouter]\n'
        'name = "OpenRouter"\n'
        f"base_url = {json.dumps(base_url)}\n"
        'wire_api = "responses"\n'
        'env_key = "OPENROUTER_API_KEY"\n'
        + (f"\n{mcp_config}" if mcp_config else ""),
        encoding="utf-8",
    )
    config.chmod(0o600)


class DeepSeekCodexBackend(CodexBackend):
    """Codex backend that configures RewardKit's isolated 0.2.0 CODEX_HOME."""

    name = "deepseek-codex"

    async def __aenter__(self) -> DeepSeekCodexBackend:
        base_url = deepseek_base_url()
        await super().__aenter__()
        try:
            openrouter_key = self.env.pop("CODEX_API_KEY", "")
            if not openrouter_key:
                raise RuntimeError("RewardKit did not initialize the judge API key")
            self.env["OPENROUTER_API_KEY"] = openrouter_key
            if self.model != "deepseek/deepseek-v4.1-flash":
                raise ValueError(
                    "the DeepSeek Codex judge model must be deepseek/deepseek-v4.1-flash"
                )
            if self.codex_home is None:
                raise RuntimeError("RewardKit did not initialize its Codex home")
            configure_codex_home(self.codex_home, base_url)
            return self
        except Exception as exc:
            await self.__aexit__(type(exc), exc, exc.__traceback__)
            raise


register_agent(DeepSeekCodexBackend)


if __name__ == "__main__":
    from rewardkit.__main__ import main

    main()
