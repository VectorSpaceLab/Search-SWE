"""Run Harbor's installed agents with scoped authentication and setup networking."""

from contextlib import contextmanager
import inspect
import os
from pathlib import Path
import re
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from harbor.agents.model_connection import PROVIDERS
from harbor.models.task.config import NetworkMode, NetworkPolicy
from harbor.utils.env import is_sensitive_env_key
from scripts.evaluation.harness_install import ManagedHarness, execute, verify_native
from scripts.evaluation.pi_trajectory import PiTrajectory
from scripts.evaluation.antigravity_trajectory import AntigravityTrajectory
from scripts.evaluation.bounded_logs import FinalizeBoundedLogs

# Native adapters read these account/provider selectors as well as API keys.
# Only explicitly selected native env values should control their auth route.
AUTH_PREFIXES = ("CLAUDE_", "ANTHROPIC_", "CODEX_", "GEMINI_", "AGY_", "OPENAI_",
                 "AWS_", "AZURE_", "GOOGLE_", "CLOUDSDK_", "GCLOUD_", "LLM_",
                 "VIBE_", "JUNIE_", "GROK_")


@contextmanager
def agent_environment(extra_env):
    """Legacy Harbor agents read os.environ directly instead of extra_env."""
    original = dict(os.environ)
    provider_vars = {name for spec in PROVIDERS.values()
                     for name in (*spec.api_key_envs, *spec.base_url_envs, *spec.extra_envs)}
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


class NativeLifecycle(ManagedHarness):
    async def setup(self, environment):
        from search_swe.harbor_native import HOST
        original = environment.network_policy
        install_hosts = set(self._search_swe_setup_hosts)
        # Include literal distribution hosts declared by this trusted Harbor adapter.
        source = Path(inspect.getfile(self._search_swe_base_class)).read_text()
        install_hosts.update(host.lower() for host in re.findall(r"https?://([A-Za-z0-9.-]+)", source)
                             if HOST.fullmatch(host.lower()))
        policy = original if original.network_mode == NetworkMode.PUBLIC else NetworkPolicy(
            network_mode=NetworkMode.ALLOWLIST,
            allowed_hosts=sorted(set(original.allowed_hosts) | install_hosts))
        try:
            if policy != original:
                await environment.set_network_policy(policy)
            with agent_environment(self.extra_env):
                if self._search_swe_files:
                    uid = (await execute(environment, "id -u")).strip()
                    if not re.fullmatch(r"[0-9]+", uid):
                        raise RuntimeError("Cannot identify the native agent's container user")
                for item in self._search_swe_files:
                    target = item["target"]
                    await execute(environment, "mkdir -p -- " + shlex.quote(str(Path(target).parent)))
                    await environment.upload_file(source_path=Path(item["source"]), target_path=target)
                    # Docker copies as root; the evaluated agent may run as a
                    # separate user. Keep its credentials private and readable.
                    quoted = shlex.quote(target)
                    await execute(environment, f"chown {uid} -- {quoted} && chmod 600 -- {quoted}", user="root")
                await super().setup(environment)
                if not self._search_swe_managed and self._search_swe_expected_version:
                    await verify_native(self, environment, self._search_swe_expected_version)
        finally:
            if policy != original:
                await environment.set_network_policy(original)

    async def run(self, *args, **kwargs):
        with agent_environment(self.extra_env):
            return await super().run(*args, **kwargs)


class NativeAgent:
    """Factory returning the actual Harbor agent with its native capabilities."""

    def __new__(cls, *args, search_swe_native_name, search_swe_setup_hosts=(),
                search_swe_files=(), **kwargs):
        from search_swe.harbor_native import agent_class, registry
        from search_swe import harnesses
        selected_version = harnesses.resolve_version(search_swe_native_name, kwargs.get("version"))
        managed = harnesses.install_spec(search_swe_native_name, selected_version)
        if selected_version:
            kwargs["version"] = selected_version
        base = agent_class(search_swe_native_name)
        if search_swe_native_name not in registry():
            from harbor.agents.installed.acp_registry import registry_spec_from_agent_name
            kwargs.setdefault("registry_spec", registry_spec_from_agent_name(search_swe_native_name))
        converter = {"pi": PiTrajectory, "antigravity-cli": AntigravityTrajectory}.get(search_swe_native_name)
        bases = (FinalizeBoundedLogs, NativeLifecycle, *((converter,) if converter else ()), base)
        adapted = type("SearchSwe" + base.__name__, bases, {"__module__": base.__module__})
        with agent_environment(kwargs.get("extra_env") or {}):
            instance = adapted(*args, **kwargs)
        instance._search_swe_base_class = base
        instance.HARNESS_NAME = search_swe_native_name
        instance._search_swe_managed = managed is not None
        instance._search_swe_expected_version = selected_version
        instance._search_swe_setup_hosts = search_swe_setup_hosts
        instance._search_swe_files = search_swe_files
        return instance
