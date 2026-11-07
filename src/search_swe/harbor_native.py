"""Discover Harbor agents and resolve their explicit, agent-only configuration."""

from functools import lru_cache
import argparse
import inspect
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ENHANCED = ("codex", "claude-code", "pi")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
REFERENCE = re.compile(r"\$\{(AGENT_[A-Z0-9_]+)\}\Z")
HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]*\Z")
OPTIONS = {"kwargs", "env", "extra_allowed_hosts", "setup_hosts", "files"}
# Only the trusted installation phase gains these package distribution hosts.
SETUP_HOSTS = (
    "antigravity.google", "dl.google.com", "storage.googleapis.com", "github.com",
    "api.github.com", "raw.githubusercontent.com", "objects.githubusercontent.com",
    "release-assets.githubusercontent.com", "registry.npmjs.org", "nodejs.org",
    "pypi.org", "files.pythonhosted.org", "astral.sh", "deb.debian.org",
    "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com",
)
AGENT_SETUP_HOSTS = {
    "antigravity-cli": ("antigravity-cli-auto-updater-974169037036.us-central1.run.app",),
}
AUTH = {
    "antigravity-cli": (("GEMINI_API_KEY", "GOOGLE_API_KEY"), "https://generativelanguage.googleapis.com"),
    "antigravity-sdk": (("GEMINI_API_KEY",), "https://generativelanguage.googleapis.com"),
    "copilot-cli": (("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"), "https://api.githubcopilot.com"),
    "cursor-cli": (("CURSOR_API_KEY",), "https://api2.cursor.sh"),
    "devin": (("DEVIN_API_KEY",), "https://api.devin.ai"),
    "grok-build": (("XAI_API_KEY",), "https://api.x.ai"),
    "junie": (("JUNIE_API_KEY",), None),
    "kimi-code": (("KIMI_MODEL_API_KEY",), "https://api.moonshot.ai/v1"),
    "vibe": (("MISTRAL_API_KEY",), "https://api.mistral.ai/v1"),
}
AGENT_HOSTS = {
    "cursor-cli": ("api2.cursor.sh", "api5.cursor.sh", "authenticate.cursor.sh", "authenticator.cursor.sh"),
    "copilot-cli": ("api.github.com", "api.githubcopilot.com", "api.individual.githubcopilot.com",
                    "api.business.githubcopilot.com", "api.enterprise.githubcopilot.com"),
}


@lru_cache(maxsize=1)
def registry():
    from harbor.agents.factory import AgentFactory
    return {name.value: path for name, path in AgentFactory._AGENT_MAP.items()}


def names():
    return (*ENHANCED, *sorted(set(registry()) - set(ENHANCED)))


def valid_name(name):
    from harbor.agents.installed.acp_registry import is_acp_registry_shorthand
    return name in registry() or is_acp_registry_shorthand(name)


def require_name(name):
    if not valid_name(name):
        raise ValueError("Unknown Harbor agent; use search-swe agents to list installed integrations")
    return name


def agent_argument(name):
    try:
        return require_name(name)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def agent_class(name):
    from harbor.agents.factory import AgentFactory
    from harbor.models.agent.name import AgentName
    require_name(name)
    return AgentFactory.get_agent_class(AgentName(name if name in registry() else "acp"))


def routes(name):
    return ("openrouter", "direct", "native") if name in ENHANCED else ("native",)


def default_route(name):
    return "direct" if name == "pi" else "openrouter" if name in ENHANCED else "native"


def check_trajectory_support(name, native, task_config):
    """Reject an incompatible evaluation before preparing task assets."""
    if (not native or name in ("oracle", "nop", "pi")
            or "/logs/agent/trajectory.json" not in task_config.get("artifacts", [])
            or agent_class(name).SUPPORTS_ATIF):
        return
    task = task_config.get("task", {}).get("name", "Selected task")
    guidance = " Choose an agent with atif=true in search-swe agents."
    raise ValueError(f"{task} requires an ATIF trajectory; {name}'s native route does not produce one." + guidance)


def describe(name, root=None):
    from . import harnesses
    cls = agent_class(name)
    parameters = set()
    for base in cls.__mro__:
        for key, parameter in inspect.signature(base.__init__).parameters.items():
            if key not in {"self", "args", "kwargs"} and parameter.kind not in (
                    inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                parameters.add(key)
    parameters.update(item.kwarg for item in [*getattr(cls, "CLI_FLAGS", ()), *getattr(cls, "ENV_VARS", ())])
    return {"name": name, "routes": list(routes(name)), "native_atif": cls.SUPPORTS_ATIF,
            "atif": cls.SUPPORTS_ATIF or name == "pi",
            "atif_source": "harbor" if cls.SUPPORTS_ATIF else "search-swe" if name == "pi" else None,
            "default_version": harnesses.default_version(name, root),
            "managed_installation": name in harnesses.registry(root)["agents"],
            "kwargs": sorted(parameters - {"logs_dir", "logger", "extra_env", "model_name", "environment_logs_dir"}),
            "source": registry().get(name, registry()["acp"])}


def hosts(values):
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) or not HOST.fullmatch(value) for value in values):
        raise ValueError("Agent hosts must be exact lowercase DNS names, without schemes, ports or wildcards")
    return sorted(set(values))


def load_options(path=None):
    if not path:
        return {}
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError()
        value = json.loads(content)
    except (OSError, ValueError):
        raise ValueError("Cannot read agent configuration: use a JSON object of kwargs, env, extra_allowed_hosts, setup_hosts and files") from None
    if not isinstance(value, dict) or set(value) - OPTIONS:
        raise ValueError("Agent configuration accepts only kwargs, env, extra_allowed_hosts, setup_hosts and files")
    reserved = {"logs_dir", "logger", "extra_env", "model_name", "task_dir", "trial_paths", "environment_logs_dir"}
    if not isinstance(value.get("kwargs", {}), dict) or any(key.startswith("search_swe_") or key in reserved for key in value.get("kwargs", {})):
        raise ValueError("Agent kwargs must be an object with native Harbor parameter names")
    for section in ("env", "files"):
        if not isinstance(value.get(section, {}), dict):
            raise ValueError(f"Agent {section} must be an object")
    for key, item in value.get("env", {}).items():
        if not ENV_NAME.fullmatch(key) or not isinstance(item, str):
            raise ValueError("Agent env maps environment names to strings")
        if "${" in item and not REFERENCE.fullmatch(item):
            raise ValueError("Agent credential references must use ${AGENT_VARIABLE_NAME}")
        from harbor.utils.env import is_sensitive_env_key
        auth_setting = key in {"AGY_ADC_AUTH", "CODEX_FORCE_AUTH_JSON", "CODEX_FORCE_OAUTH", "GEMINI_FORCE_OAUTH",
                               "GOOGLE_APPLICATION_CREDENTIALS"} or key.endswith(("_PATH", "_FILE"))
        if item and (is_sensitive_env_key(key) or key.endswith("_PAT")) and not auth_setting and not REFERENCE.fullmatch(item):
            raise ValueError("Agent credentials must reference ${AGENT_VARIABLE_NAME}; put their values in the private .env")
    for source, target in value.get("files", {}).items():
        if not REFERENCE.fullmatch(source) or not isinstance(target, str) or not target.startswith("/") or ".." in Path(target).parts:
            raise ValueError("Agent files maps ${AGENT_FILE_VARIABLE} to an absolute container file path")
    for section in ("extra_allowed_hosts", "setup_hosts"):
        hosts(value.get(section, []))
    return value


def plan(name, model, env, config=None):
    """Resolve references, never credential values, for the selected native agent."""
    cls = agent_class(name)
    options = load_options(config)
    from harbor.agents.model_connection import ModelConnectionSpec, PROVIDERS, resolve_model_connection
    spec = getattr(cls, "MODEL_CONNECTION", None) or ModelConnectionSpec()
    provider = None
    prefix, separator, remainder = (model or "").partition("/")
    byok = None
    if name == "grok-build" and separator and remainder and prefix in cls._PROVIDERS:
        native = cls._PROVIDERS[prefix]
        provider = prefix
        byok = ((native["env_key"],), native["base_url"])
    elif name == "junie" and separator:
        from harbor.agents.installed.junie import _PROVIDER_ALIASES, _PROVIDER_KEY_ENV
        provider = _PROVIDER_ALIASES.get(prefix.lower())
        if provider is None:
            raise ValueError("Unsupported Junie BYOK provider; use a supported provider/model or a bare JetBrains model name")
        primary, fallbacks = _PROVIDER_KEY_ENV[provider]
        byok = ((primary, *fallbacks), PROVIDERS[provider].base_url)
    vibe_backend = options.get("env", {}).get("VIBE_BACKEND", options.get("kwargs", {}).get("backend") or "mistral")
    match = REFERENCE.fullmatch(vibe_backend) if isinstance(vibe_backend, str) else None
    if match:
        vibe_backend = env.get(match[1], "mistral")
    vibe_generic = name == "vibe" and isinstance(vibe_backend, str) and vibe_backend.lower() == "generic"
    if byok is None and (name not in AUTH and name != "rovodev-cli" or vibe_generic):
        # Fixed-service agents own their authentication. Other routes use
        # Harbor's inference without reading host credentials or endpoints.
        provider = resolve_model_connection(model, spec, lambda *names: None).provider
    access = PROVIDERS.get(provider)
    key_names = tuple(dict.fromkeys((*getattr(spec, "api_key_envs", ()), *(access.api_key_envs if access else ()))))
    provider_base_names = access.base_url_envs if access else ((provider.upper().replace("-", "_") + "_BASE_URL",) if provider else ())
    base_names = tuple(dict.fromkeys((*getattr(spec, "base_url_envs", ()), *provider_base_names)))
    endpoint = access.base_url if access else None
    if byok:
        key_names, endpoint = byok
        base_names = ()  # These Harbor adapters use their fixed provider URLs.
    elif vibe_generic:
        key_names = access.api_key_envs if access else ("OPENAI_API_KEY",)
        base_names = tuple(dict.fromkeys(("VIBE_API_BASE", *base_names,
                                          *(("OPENAI_BASE_URL",) if not access else ()))))
    elif name in AUTH:
        key_names, endpoint = AUTH[name]
        if name == "antigravity-cli":
            base_names = ("GOOGLE_GEMINI_BASE_URL",)
        elif name == "vibe":
            base_names = ("VIBE_API_BASE",)
    if name in ("oracle", "nop", "acp") or name not in registry():
        key_names, base_names, endpoint = (), (), None
    if name == "rovodev-cli":
        key_names, endpoint = (), "https://api.atlassian.com"
    bindings = dict(options.get("env", {}))
    # An explicit native env block defines its own authentication strategy (e.g. ADC).
    if not bindings and key_names:
        target = next((key for key in key_names if env.get("AGENT_" + key, "").strip()), key_names[0])
        bindings["OPENAI_API_KEY" if vibe_generic else target] = "${AGENT_" + target + "}"
    if name == "rovodev-cli" and not bindings:
        bindings = {key: "${AGENT_" + key + "}" for key in ("ROVODEV_USER_EMAIL", "ROVODEV_USER_API_TOKEN")}
    for key in (*base_names, *(access.extra_envs if access else ())):
        source = "AGENT_" + key
        if source in env and env[source].strip() and key not in bindings:
            bindings[key] = "${" + source + "}"
    for key in base_names:
        if key in bindings:
            match = REFERENCE.fullmatch(bindings[key])
            configured = env.get(match[1], "") if match else bindings[key]
            if configured:
                endpoint = configured
                break
    if vibe_generic and endpoint and not any(key in bindings for key in ("VIBE_API_BASE", "OPENAI_BASE_URL")):
        # Vibe's generic backend requires an explicit endpoint even for known
        # providers. Preserve references for configured endpoint overrides.
        bindings["VIBE_API_BASE"] = next((bindings[key] for key in base_names if key in bindings), endpoint)
    allowed = [*AGENT_HOSTS.get(name, ()), *options.get("extra_allowed_hosts", [])]
    if endpoint:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Native agent endpoint must be an HTTP(S) URL without credentials, query or fragment")
        allowed.append(parsed.hostname)
    required = {match[1] for value in bindings.values() if (match := REFERENCE.fullmatch(value))}
    required.update(REFERENCE.fullmatch(value)[1] for value in options.get("files", {}))
    return {"env": bindings, "required": required, "hosts": hosts(allowed),
            "kwargs": options.get("kwargs", {}), "files": options.get("files", {}),
            "setup_hosts": hosts([*SETUP_HOSTS, *allowed, *AGENT_SETUP_HOSTS.get(name, ()), *options.get("setup_hosts", [])])}


def display(name=None, *, as_json=False, root=None):
    rows = [describe(name, root)] if name else [describe(item, root) for item in names()]
    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        for item in rows:
            print(f"{item['name']:<24} {', '.join(item['routes']):<28} version: {item['default_version'] or 'native default':<12} ATIF: {item['atif']} ({item['atif_source'] or 'unavailable'})")
        print("Use --provider native and --agent-config PATH for Harbor credentials, kwargs and endpoint hosts. See docs/evaluation/agents.md.")
