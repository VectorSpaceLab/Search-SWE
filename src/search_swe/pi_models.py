"""Pi's pinned API-key provider catalog and selected-provider configuration."""

from functools import lru_cache
from importlib.resources import files
import json
import re
from urllib.parse import urlsplit

MODEL_ID = re.compile(r"[a-z0-9][a-z0-9-]*/[a-zA-Z0-9~@][a-zA-Z0-9._:/@+~-]*")
HOST_KEYS = {"OPENAI_API_KEY": "AGENT_OPENAI_API_KEY", "ANTHROPIC_API_KEY": "AGENT_ANTHROPIC_API_KEY",
             "OPENROUTER_API_KEY": "AGENT_OPENROUTER_API_KEY", "HF_TOKEN": "AGENT_HF_TOKEN"}
EXTRA_VARIABLES = {
    "amazon-bedrock": ("AWS_REGION",),
    "azure": ("AZURE_OPENAI_BASE_URL", "AZURE_OPENAI_RESOURCE_NAME", "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_DEPLOYMENT_NAME_MAP"),
    "cloudflare-ai-gateway": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_GATEWAY_ID"),
    "cloudflare-workers-ai": ("CLOUDFLARE_ACCOUNT_ID",),
}


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files("search_swe").joinpath("data/pi-models.json").read_text())


def selection(model):
    if not MODEL_ID.fullmatch(model):
        raise ValueError("Pi requires a complete provider/model ID; see search-swe pi-models")
    provider, model_id = model.split("/", 1)
    info = catalog()["providers"].get(provider)
    if info is None:
        raise ValueError(f"Unsupported Pi API-key provider: {provider}; see search-swe pi-models")
    if model_id not in info["models"] and provider != "openrouter":
        raise ValueError(f"Unknown model for Pi {catalog()['version']}: {model}; "
                         f"see search-swe pi-models --provider {provider}")
    return provider, model_id, info


def native_model(model, route):
    return "openrouter/" + model if route == "openrouter" else model


def resolve_model_config(model, *, offline=False, refresh=False):
    """Resolve new OpenRouter models before assets or containers are prepared."""
    provider, model_id, info = selection(model)
    if provider != "openrouter" or model_id in info["models"]:
        return None
    from .model_catalog import eligible, load_models
    models, _ = load_models(offline=offline, refresh=refresh)
    metadata = models.get(model_id)
    if not metadata or not eligible(metadata, "pi"):
        remedy = "Refresh the catalog without --offline" if offline else "Check the model ID or refresh the OpenRouter catalog"
        raise ValueError(f"Pi needs compatible catalog metadata for {model_id}. {remedy}, "
                         "or select a bundled model with search-swe pi-models --provider openrouter.")
    config = {"id": model_id, "name": metadata["name"],
              "reasoning": bool({"reasoning", "reasoning_effort"}.intersection(metadata.get("supported_parameters", []))),
              "contextWindow": metadata.get("context_length", 128000),
              "maxTokens": metadata.get("max_output_tokens", 16384),
              "input": [kind for kind in metadata.get("input_modalities", ["text"]) if kind in ("text", "image")]}
    if "cost" in metadata:
        config["cost"] = metadata["cost"]
    return config


def validate_model_config(model, config):
    provider, model_id, _ = selection(model)
    if (provider != "openrouter" or not isinstance(config, dict) or config.get("id") != model_id
            or set(config) - {"id", "name", "reasoning", "contextWindow", "maxTokens", "input", "cost"}
            or not isinstance(config.get("name"), str) or type(config.get("reasoning")) is not bool
            or any(type(config.get(key)) is not int or config[key] <= 0 for key in ("contextWindow", "maxTokens"))
            or not isinstance(config.get("input"), list) or not config["input"]
            or any(kind not in ("text", "image") for kind in config["input"])):
        raise ValueError("Pi model configuration does not match the selected OpenRouter model")
    return config


def required_variables(model, env=None):
    env = env or {}
    provider, _, info = selection(model)
    required = {HOST_KEYS.get(key, key) for key in info["keys"]}
    if provider == "azure":
        required.add("AZURE_OPENAI_RESOURCE_NAME" if env.get("AZURE_OPENAI_RESOURCE_NAME") and not env.get("AZURE_OPENAI_BASE_URL")
                     else "AZURE_OPENAI_BASE_URL")
    elif provider == "amazon-bedrock":
        required.add("AWS_REGION")
    elif provider.startswith("cloudflare-"):
        required.update(EXTRA_VARIABLES[provider])
    return required


def env_bindings(model, env=None):
    env = env or {}
    provider, _, info = selection(model)
    bindings = {key: HOST_KEYS.get(key, key) for key in info["keys"]}
    for key in EXTRA_VARIABLES.get(provider, ()):
        if key in required_variables(model, env) or env.get(key):
            bindings[key] = key
    return bindings


def endpoint_host(url, name):
    parsed = urlsplit(url)
    try:
        parsed.port
    except ValueError:
        raise ValueError(f"{name} has an invalid port") from None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or "{" in parsed.netloc or "}" in parsed.netloc):
        raise ValueError(f"{name} must be an HTTPS URL without credentials, query or fragment")
    return parsed.hostname.lower().rstrip(".")


def agent_host(model, env, *, preview=False):
    provider, model_id, info = selection(model)
    if provider == "azure":
        base = env.get("AZURE_OPENAI_BASE_URL")
        if base:
            return endpoint_host(base, "AZURE_OPENAI_BASE_URL")
        resource = env.get("AZURE_OPENAI_RESOURCE_NAME")
        if resource and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", resource):
            return resource.lower() + ".openai.azure.com"
        if preview and not resource:
            return "your-resource.openai.azure.com"
        raise ValueError("Configure AZURE_OPENAI_BASE_URL or a valid AZURE_OPENAI_RESOURCE_NAME")
    if provider == "amazon-bedrock":
        region = env.get("AWS_REGION") or ("us-east-1" if preview else "")
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", region):
            raise ValueError("Set AWS_REGION to the Bedrock model's AWS region")
        suffix = "amazonaws.com.cn" if region.startswith("cn-") else "amazonaws.com"
        return f"bedrock-runtime.{region}.{suffix}"
    if provider == "google-vertex":
        return "aiplatform.googleapis.com"  # Vertex API-key (express) mode.
    if provider.startswith("cloudflare-"):
        for name in EXTRA_VARIABLES[provider]:
            value = env.get(name, "")
            if value and not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError(f"{name} must be an account/gateway identifier")
        return "gateway.ai.cloudflare.com" if provider == "cloudflare-ai-gateway" else "api.cloudflare.com"
    url = info["models"].get(model_id, {}).get("base_url") or info["base_url"]
    return endpoint_host(url, "Pi model endpoint")


def display(provider=None, *, as_json=False):
    data = catalog()
    if provider:
        info = data["providers"].get(provider)
        if info is None:
            raise ValueError(f"Unknown Pi provider: {provider}; see search-swe pi-models")
        rows = [{"id": name if provider == "openrouter" and "/" in name else provider + "/" + name,
                 "provider": "openrouter" if provider == "openrouter" and "/" in name else "direct",
                 "native_id": provider + "/" + name, **model} for name, model in info["models"].items()]
    else:
        rows = [{"provider": name, "name": info["name"], "model_count": len(info["models"]),
                 "key_variables": [HOST_KEYS.get(key, key) for key in info["keys"]]}
                for name, info in data["providers"].items()]
    if as_json:
        print(json.dumps({"pi_version": data["version"], "source": data["source"],
                          "models" if provider else "providers": rows}, indent=2))
    else:
        print(f"Pi {data['version']} · API-key providers and chat models")
        if provider:
            print("Use these flags with: search-swe run TASK --agent pi")
        for row in rows:
            if provider:
                print(f"--provider {row['provider']:<10} --model {row['id']:<70} {row['name']}")
            else:
                print(f"{row['provider']:<28} {row['model_count']:>4} models  {', '.join(row['key_variables'])}")
        if not provider:
            print("Show models: search-swe pi-models --provider PROVIDER")
