"""Run Harbor's installed agents with scoped authentication and setup networking."""

import inspect
from pathlib import Path
import re
import shlex
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from scripts.evaluation.harbor_auth import ScopedHarborAuth, agent_environment
from harbor.models.task.config import NetworkMode, NetworkPolicy
from scripts.evaluation.harness_install import ManagedHarness, execute, verify_native
from scripts.evaluation.pi_trajectory import PiTrajectory
from scripts.evaluation.antigravity_trajectory import AntigravityTrajectory
from scripts.evaluation.bounded_logs import FinalizeBoundedLogs

class NativeLifecycle(ScopedHarborAuth, ManagedHarness):
    def __init__(self, *args, search_swe_native_name=None, search_swe_setup_hosts=(), search_swe_files=(), **kwargs):
        from search_swe import harnesses
        from search_swe.harbor_native import registry
        self.HARNESS_NAME = search_swe_native_name or self.HARNESS_NAME
        selected = harnesses.resolve_version(self.HARNESS_NAME, kwargs.get("version"))
        self._search_swe_expected_version = selected
        self._search_swe_managed = harnesses.install_spec(self.HARNESS_NAME, selected) is not None
        self._search_swe_setup_hosts = search_swe_setup_hosts
        self._search_swe_files = search_swe_files
        if selected:
            kwargs["version"] = selected
        if self.HARNESS_NAME not in registry():
            from harbor.agents.installed.acp_registry import registry_spec_from_agent_name
            kwargs.setdefault("registry_spec", registry_spec_from_agent_name(self.HARNESS_NAME))
        if kwargs.get("model_name"):
            from search_swe.harbor_native import native_model
            kwargs["model_name"] = native_model(self.HARNESS_NAME, kwargs["model_name"])
        with agent_environment(kwargs.get("extra_env") or {}):
            super().__init__(*args, **kwargs)

    @classmethod
    def parse_options(cls, kwargs=None, env=None):
        options = dict(kwargs or {})
        for key in ("search_swe_native_name", "search_swe_setup_hosts", "search_swe_files"):
            options.pop(key, None)
        return super().parse_options(options, env)

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
            with agent_environment(self._extra_env if hasattr(self, "_extra_env") else self.extra_env):
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
        with agent_environment(self._extra_env if hasattr(self, "_extra_env") else self.extra_env):
            return await super().run(*args, **kwargs)


class AntigravityOpenRouter:
    """Run Harbor's agy commands against the per-process Gemini bridge."""

    def _parse_model_name(self, model_name):
        return "gemini", model_name.rsplit("/", 1)[-1]

    @classmethod
    def resolve_model_connection_config(cls, model_name, resolve_env, **options):
        # The local bridge speaks Gemini and owns the outbound provider selection.
        return super().resolve_model_connection_config("gemini/bridge", resolve_env, **options)

    def _find_api_key(self):
        # Enable Harbor's headless Gemini configuration. The bridge generates
        # the actual loopback key and hands it to the agy child process.
        return "search-swe-loopback"

    async def run(self, instruction, environment, context):
        if not self._get_env("AGENT_OPENROUTER_API_KEY"):
            raise ValueError("Antigravity OpenRouter requires AGENT_OPENROUTER_API_KEY")
        self._bridge_path = f"/tmp/search-swe-agy-{uuid4().hex}.py"
        await environment.upload_file(Path(__file__).with_name("agy_openrouter.py"), self._bridge_path)
        return await super().run(instruction, environment, context)

    async def exec_as_agent(self, environment, command, env=None, **kwargs):
        if (env or {}).get("GEMINI_API_KEY") == "search-swe-loopback":
            if not command.startswith("$HOME/.local/bin/agy "):
                raise RuntimeError("Harbor's Antigravity command format changed")
            env = {**env, "AGENT_OPENROUTER_API_KEY": self._get_env("AGENT_OPENROUTER_API_KEY")}
            command = (f"/opt/conda/bin/python -I {shlex.quote(self._bridge_path)} "
                       f"{shlex.quote(self.model_name)} " + command)
        return await super().exec_as_agent(environment, command, env=env, **kwargs)


def native_class(name, openrouter=False):
    from search_swe.harbor_native import agent_class
    base = agent_class(name)
    converter = {"pi": PiTrajectory, "antigravity-cli": AntigravityTrajectory}.get(name)
    mixins = (converter,) if converter else ()
    if openrouter:
        if name != "antigravity-cli":
            raise ValueError("The Gemini bridge is only available for Antigravity CLI")
        mixins += (AntigravityOpenRouter,)
    attributes = {"_search_swe_base_class": base, "__module__": __name__}
    if name == "pi" and hasattr(base, "capabilities"):
        attributes["capabilities"] = base.capabilities.model_copy(update={"atif": True})
    return type("SearchSwe" + base.__name__, (FinalizeBoundedLogs, NativeLifecycle, *mixins, base), attributes)


def __getattr__(attribute):
    # Harbor resolves the concrete class, including its auth and options schema,
    # during preflight, before it constructs an agent.
    if attribute == "OpenRouterAntigravity":
        return native_class("antigravity-cli", openrouter=True)
    if attribute.startswith("Harness_"):
        from search_swe.harbor_native import registry
        name = attribute.removeprefix("Harness_").replace("_", "-")
        if name in registry():
            return native_class(name)
    raise AttributeError(attribute)


class NativeAgent:
    """Constructor for existing job configurations."""

    def __new__(cls, *args, search_swe_native_name, search_swe_openrouter=False, **kwargs):
        return native_class(search_swe_native_name, search_swe_openrouter)(
            *args, search_swe_native_name=search_swe_native_name, **kwargs)
