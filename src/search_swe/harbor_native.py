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
    if name == "antigravity-cli":
        return ("native", "openrouter")
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


def _native_parameters(cls):
    if schema := getattr(cls, "options_model", None):
        parameters = set(schema.model_fields)
        for name in ("base_url", "reasoning_effort"):
            if getattr(cls.capabilities, name, None) is False:
                parameters.discard(name)
        if getattr(cls, "resolve_model_connection_for_execution", None) and cls.MODEL_CONNECTION is not None:
            parameters.update(("model_api_key_name", "model_api_format"))
        return parameters
    # Older Harbor agents expose constructor parameters and CLI flags directly.
    parameters = set()
    for base in cls.__mro__:
        for key, parameter in inspect.signature(base.__init__).parameters.items():
            if key not in {"self", "args", "kwargs"} and parameter.kind not in (
                    inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                parameters.add(key)
    parameters.update(item.kwarg for item in [*getattr(cls, "CLI_FLAGS", ()), *getattr(cls, "ENV_VARS", ())])
    if getattr(cls, "MODEL_CONNECTION", None) is None:
        parameters.difference_update(("model_api_key_name", "model_api_format"))
    return parameters - {"logs_dir", "logger", "extra_env", "model_name", "environment_logs_dir", "task_dir", "trial_paths"}


def describe(name, root=None):
    from . import harnesses
    cls = agent_class(name)
    return {"name": name, "routes": list(routes(name)), "native_atif": cls.SUPPORTS_ATIF,
            "atif": cls.SUPPORTS_ATIF or name == "pi",
            "atif_source": "search-swe" if name == "pi" else "harbor" if cls.SUPPORTS_ATIF else None,
            "default_version": harnesses.default_version(name, root),
            "managed_installation": name in harnesses.registry(root)["agents"],
            "kwargs": sorted(_native_parameters(cls)),
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


def native_model(name, model):
    from .harbor_compat import HARBOR_VERSION
    if HARBOR_VERSION.release[:2] >= (0, 25) and model and "/" in model:
        provider, model_id = model.split("/", 1)
        if name == "junie":
            from harbor.agents.installed.junie import _PROVIDER_ALIASES
            provider = _PROVIDER_ALIASES.get(provider.lower(), provider)
        if name in {"junie", "grok-build"}:
            return ("gemini" if provider == "google" else provider) + "/" + model_id
    return model


def _auth_flag(value, name):
    from harbor.utils.env import parse_bool_env_value
    try:
        return parse_bool_env_value(value.strip() or "false", name=name)
    except ValueError:
        raise ValueError(f"{name} must be a boolean, such as true or false") from None


def _configure_antigravity_auth(model, bindings, env, selector):
    from .harbor_compat import HARBOR_VERSION, PROVIDERS, provider_variables

    if not model or (HARBOR_VERSION.release[:2] < (0, 25) and "/" not in model):
        raise ValueError("Antigravity CLI requires an explicit model ID, e.g. gemini/gemini-3-flash")
    flag = bindings.get("AGY_ADC_AUTH", "")
    if reference := REFERENCE.fullmatch(flag):
        flag = env.get(reference[1], "")
        if not flag.strip():
            return None  # The wizard requests the referenced authentication setting.
    gemini_keys = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY")
    gateway_key = "AGY_LLM_GATEWAY_API_KEY"
    if _auth_flag(flag, "AGY_ADC_AUTH"):
        if selector is not None:
            raise ValueError("Antigravity ADC uses cloud credentials; an API key selector requires API-key mode")
        if "2.5" in model.split("/", 1)[-1]:
            raise ValueError("Antigravity ADC requires Gemini 3 Flash or newer; Gemini 2.5 uses API-key authentication")
        for key in (*gemini_keys, gateway_key, "AGY_LLM_GATEWAY_URL", "GOOGLE_GEMINI_BASE_URL"):
            bindings.pop(key, None)
        return "adc"
    gateway = bool(bindings.get("AGY_LLM_GATEWAY_URL"))
    if gateway and HARBOR_VERSION.release[:2] < (0, 26):
        raise ValueError("Native Antigravity LLM gateway mode requires Harbor 0.26 or later")
    if HARBOR_VERSION.release[:2] < (0, 25) and bindings and not any(bindings.get(key) for key in gemini_keys[:2]):
        raise ValueError("Bind GEMINI_API_KEY to a ${AGENT_VARIABLE_NAME} credential in the native env configuration")
    # Keep an explicit gateway credential ahead of any co-configured Gemini
    # aliases. Harbor's default provider precedence otherwise picks a Google key.
    selected = selector or (gateway_key if gateway and bindings.get(gateway_key) else None)
    auth_keys = {key for access in PROVIDERS.values() for key in provider_variables(access)[0]}
    auth_keys.update((*gemini_keys, gateway_key))
    for key in auth_keys.intersection(bindings):
        if not bindings[key] or (selected and key != selected) or (key == gateway_key and not gateway and key != selector):
            bindings.pop(key, None)
    return "gateway" if gateway else "gemini"


def plan(name, model, env, config=None):
    """Resolve references, never credential values, for the selected native agent."""
    cls = agent_class(name)
    options = load_options(config)
    from .harbor_compat import ModelConnectionSpec, PROVIDERS, provider_variables, resolve_model_connection
    spec = getattr(cls, "MODEL_CONNECTION", None) or ModelConnectionSpec()
    provider = None
    prefix, separator, remainder = (model or "").partition("/")
    # Newer native adapters can use either their own service or a model provider.
    native_service = {"grok-build": "xai", "kimi-code": "moonshot", "copilot-cli": "github-copilot"}.get(name)
    resolve_execution = getattr(cls, "resolve_model_connection_for_execution", None)
    provider_aware = native_service is not None and resolve_execution is not None
    byok = None
    if name == "grok-build" and separator and remainder and prefix in getattr(cls, "_PROVIDERS", {}):
        native = cls._PROVIDERS[prefix]
        provider = prefix
        byok = ((native["env_key"],), native["base_url"])
    elif name == "junie":
        from harbor.agents.installed.junie import _PROVIDER_ALIASES, _PROVIDER_KEY_ENV
        if separator:
            provider = _PROVIDER_ALIASES.get(prefix.lower())
            if provider is None:
                raise ValueError("Unsupported Junie BYOK provider; use a supported provider/model or a bare JetBrains model name")
        elif resolve_execution:
            from harbor.agents.installed.junie import _junie_provider
            provider = _junie_provider(model)
        if provider:
            primary, fallbacks = _PROVIDER_KEY_ENV[provider]
            harbor_provider = "gemini" if provider == "google" and provider not in PROVIDERS else provider
            byok = ((primary, *fallbacks), PROVIDERS[harbor_provider].base_url)
    model_routed = (name not in AUTH and name != "rovodev-cli") or provider_aware
    infer_provider = model_routed or name == "vibe"
    if byok is None and infer_provider:
        if name == "copilot-cli":
            # A bare Copilot catalog name keeps GitHub subscription auth.
            provider = cls.resolve_model_connection_config(model, lambda *names: None).provider
        else:
            provider = resolve_model_connection(native_model(name, model), spec, lambda *names: None).provider
    vibe_backend = options.get("env", {}).get("VIBE_BACKEND", options.get("kwargs", {}).get("backend"))
    match = REFERENCE.fullmatch(vibe_backend) if isinstance(vibe_backend, str) else None
    if match:
        vibe_backend = env.get(match[1])
    if name == "vibe" and not vibe_backend:
        vibe_backend = "generic" if resolve_execution and provider not in (None, "mistral") else "mistral"
    vibe_generic = name == "vibe" and isinstance(vibe_backend, str) and vibe_backend.lower() == "generic"
    if name == "vibe" and not vibe_generic:
        if resolve_execution and provider not in (None, "mistral"):
            raise ValueError(f"Vibe needs its generic backend for provider {provider!r}")
        provider = None
    if (model_routed or vibe_generic) and provider is None and separator and ("AGENT_" + prefix.upper().replace("-", "_") + "_BASE_URL") in env:
        provider = prefix
    external_provider = provider_aware and provider is not None and provider != native_service
    provider_auth = external_provider or (provider_aware and name == "kimi-code" and provider == "moonshot")
    access = PROVIDERS.get(provider)
    keys, urls, extras = provider_variables(access) if access else ((), (), ())
    native_access = getattr(spec, "agent_provider_access", None)
    native_keys, native_urls = (provider_variables(native_access)[:2] if native_access else
                                (getattr(spec, "api_key_envs", ()), getattr(spec, "base_url_envs", ())))
    if external_provider:
        # A shared .env may also contain the native service's key and endpoint.
        # An external provider uses only its own automatic bindings.
        native_keys, native_urls = (), ()
    provider_base_names = urls if access else ((provider.upper().replace("-", "_") + "_BASE_URL",) if provider else ())
    # A shared .env may configure several providers. Keep agent-specific
    # aliases, but never select another provider's key or endpoint implicitly.
    if access:
        other_keys, other_urls = set(), set()
        for other in PROVIDERS.values():
            names, endpoints, _ = provider_variables(other)
            other_keys.update(names)
            other_urls.update(endpoints)
        native_keys = [key for key in native_keys if key not in other_keys]
        native_urls = [url for url in native_urls if url not in other_urls]
    key_names = tuple(dict.fromkeys((*keys, *native_keys)))
    base_names = tuple(dict.fromkeys((*provider_base_names, *native_urls)))
    endpoint = access.base_url if access else None
    if byok:
        key_names, endpoint = byok
        base_names = ()  # These Harbor adapters use their fixed provider URLs.
    elif vibe_generic:
        key_names = keys if access else ("OPENAI_API_KEY",)
        base_names = tuple(dict.fromkeys(("VIBE_API_BASE", *urls,
                                          *(("OPENAI_BASE_URL",) if not access else ()))))
    elif name in AUTH and not provider_auth:
        key_names, endpoint = AUTH[name]
        if name == "antigravity-cli":
            base_names = ("GOOGLE_GEMINI_BASE_URL",)
        elif name == "vibe":
            base_names = ("VIBE_API_BASE",)
        elif name == "kimi-code":
            base_names = ("KIMI_MODEL_BASE_URL",)
        elif name == "devin":
            base_names = ("DEVIN_API_SERVER_URL",)
    if name in ("oracle", "nop", "acp") or name not in registry():
        key_names, base_names, endpoint = (), (), None
    if name == "rovodev-cli":
        key_names, endpoint = (), "https://api.atlassian.com"
    bindings = dict(options.get("env", {}))
    kwargs = options.get("kwargs", {})
    selector = kwargs.get("model_api_key_name")
    if selector is not None:
        if not resolve_execution or cls.MODEL_CONNECTION is None:
            raise ValueError("model_api_key_name needs Harbor 0.25 or later and a native agent with a model connection")
        if not isinstance(selector, str) or not ENV_NAME.fullmatch(selector):
            raise ValueError("model_api_key_name must name an uppercase environment variable")
        reference = bindings.setdefault(selector, "${AGENT_" + selector + "}")
        if reference and not REFERENCE.fullmatch(reference):
            raise ValueError("The selected model credential must reference ${AGENT_VARIABLE_NAME}")
    schema = getattr(cls, "options_model", None)
    if kwargs and schema and schema.model_config.get("extra") == "forbid":
        unknown = kwargs.keys() - _native_parameters(cls)
        if unknown:
            raise ValueError(f"Unsupported {name} kwargs: {', '.join(sorted(unknown))}. See search-swe agents --agent {name} --json")
    agy_mode = _configure_antigravity_auth(model, bindings, env, selector) if name == "antigravity-cli" else None
    if agy_mode in ("adc", "gateway"):
        base_names = ()  # These modes do not use the ordinary Gemini base URL.
    # An explicit native env block defines its own authentication strategy (e.g. ADC).
    if not options.get("env") and not bindings and key_names:
        target = next((key for key in key_names if env.get("AGENT_" + key, "").strip()), key_names[0])
        bindings["OPENAI_API_KEY" if vibe_generic else target] = "${AGENT_" + target + "}"
    if name == "rovodev-cli" and not bindings:
        bindings = {key: "${AGENT_" + key + "}" for key in ("ROVODEV_USER_EMAIL", "ROVODEV_USER_API_TOKEN")}
    for key in (*base_names, *extras):
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
    service_hosts = AGENT_HOSTS.get(name, ())
    has_model_route = (model or name == "copilot-cli") and (model_routed or vibe_generic)
    if resolve_execution and ((has_model_route and cls.MODEL_CONNECTION is not None)
                              or agy_mode or selector or "base_url" in kwargs):
        # Ask Harbor which host it will use, with only this agent's configured
        # inputs. Its common connection options sit outside the agent kwargs.
        explicit = {key: env.get(match[1], "") if (match := REFERENCE.fullmatch(value)) else value
                    for key, value in bindings.items()}
        def resolve_env(*names):
            return next(((key, explicit[key]) for key in names if key in explicit), None)

        connection = resolve_execution(
            native_model(name, model), resolve_env, explicit_env=explicit, kwargs=kwargs,
            base_url=kwargs.get("base_url"), model_api_format=kwargs.get("model_api_format"),
            model_api_key_name=selector)
        if selector and bindings.get(selector) == "":
            # Some custom endpoints accept an explicitly empty key. Use the
            # selected harness's preflight contract for that configuration.
            cls.check_model_credentials(connection, kwargs={**kwargs, "model_name": native_model(name, model)},
                                        env=explicit, explicit_env=explicit)
        if agy_mode in ("gateway", "gemini") and not connection.api_key:
            # Harbor also reports the selected variable when its reference is
            # waiting for wizard input. A gateway URL reference is resolved
            # before Harbor can determine its wire protocol and key candidates.
            pending_gateway = agy_mode == "gateway" and not explicit.get("AGY_LLM_GATEWAY_URL")
            if not pending_gateway and not REFERENCE.fullmatch(bindings.get(connection.api_key_source_name, "")):
                key = selector or ("AGY_LLM_GATEWAY_API_KEY" if agy_mode == "gateway" else "GEMINI_API_KEY")
                raise ValueError(f"Bind {key} to a ${{AGENT_VARIABLE_NAME}} credential in the native env configuration")
        if connection.inference_base_url:
            endpoint = connection.inference_base_url
        if agy_mode == "gateway" and (gateway := explicit.get("AGY_LLM_GATEWAY_URL")):
            import logging
            from harbor.agents.installed.antigravity_base_url import validate_base_url
            if gateway.rstrip("/") != (connection.execution_base_url or "").rstrip("/"):
                raise ValueError("Antigravity gateway conflicts with another model endpoint. Use AGY_LLM_GATEWAY_URL as the gateway address.")
            flag = "HARBOR_ALLOW_INSECURE_MODEL_BASE_URL"
            if gateway.lower().startswith("http:") and explicit.get(flag):
                _auth_flag(explicit[flag], flag)
            validate_base_url(gateway, explicit.get, logging.getLogger(__name__))
        if name == "copilot-cli" and cls._uses_custom_provider(connection):
            service_hosts = ()
    allowed = [*service_hosts, *options.get("extra_allowed_hosts", [])]
    if endpoint and agy_mode != "adc":
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Native agent endpoint must be an HTTP(S) URL without credentials, query or fragment")
        allowed.append(parsed.hostname)
    from harbor.utils.env import is_sensitive_env_key
    sources = {key: match[1] for key, value in bindings.items() if (match := REFERENCE.fullmatch(value))}
    required = set(sources.values())
    required.update(REFERENCE.fullmatch(value)[1] for value in options.get("files", {}))
    secrets = {source for key, source in sources.items()
               if key == selector or key in key_names or is_sensitive_env_key(key) or key.endswith("_PAT")}
    return {"env": bindings, "required": required, "secret_variables": secrets, "hosts": hosts(allowed),
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
