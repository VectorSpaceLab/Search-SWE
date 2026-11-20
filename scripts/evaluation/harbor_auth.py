"""Limit Harbor agent authentication to the explicitly configured environment."""

from contextlib import contextmanager
import os

from harbor.utils.env import is_sensitive_env_key
from src.search_swe.harbor_compat import PROVIDERS, provider_variables

# Native adapters read these account/provider selectors as well as API keys.
# Only explicitly selected native env values should control their auth route.
AUTH_PREFIXES = ("CLAUDE_", "ANTHROPIC_", "CODEX_", "GEMINI_", "AGY_", "OPENAI_",
                 "AWS_", "AZURE_", "GOOGLE_", "CLOUDSDK_", "GCLOUD_", "LLM_",
                 "VIBE_", "JUNIE_", "GROK_", "DEVIN_")


@contextmanager
def agent_environment(extra_env):
    """Legacy Harbor agents read os.environ directly instead of extra_env."""
    original = dict(os.environ)
    provider_vars = {name for spec in PROVIDERS.values()
                     for group in provider_variables(spec) for name in group}
    isolated = {name: value for name, value in original.items()
                if name not in provider_vars and not is_sensitive_env_key(name) and not name.endswith("_PAT")
                and not name.startswith((*AUTH_PREFIXES, "AGENT_", "VERIFIER_", "ANSWER_JUDGE_", "TRAJECTORY_JUDGE_"))}
    try:
        os.environ.clear()
        os.environ.update(isolated)
        os.environ.update(extra_env)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


class ScopedHarborAuth:
    @classmethod
    def preflight(cls, kwargs=None, env=None):
        with agent_environment(env or {}):
            return super().preflight(kwargs=kwargs, env=env)

    @classmethod
    def resolve_model_connection_config(cls, model_name, resolve_env, **options):
        # Harbor also calls this class hook before constructing the agent.
        # Its resolver falls back to the process environment.
        with agent_environment(options.get("explicit_env") or {}):
            return super().resolve_model_connection_config(model_name, resolve_env, **options)

    @classmethod
    def check_model_credentials(cls, connection, *, kwargs, env, explicit_env=None):
        with agent_environment(explicit_env or {}):
            return super().check_model_credentials(connection, kwargs=kwargs, env=os.environ,
                                                   explicit_env=explicit_env)
