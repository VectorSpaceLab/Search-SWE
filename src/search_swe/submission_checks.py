"""Mandatory sampled OpenRouter model-access checks for enabled submission keys."""

from http.client import HTTPException
import json
import re
import secrets
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .model_catalog import load_models
from .submission_models import DOC_URL, PROFILES, model_ids

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
PROBE_COUNT = 3
MIN_POOL_SIZE = 25
MAX_RESPONSE_BYTES = 64 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A submission credential is sent only to the official endpoint.


def probe_models(profile, catalog):
    allowed = set(model_ids(profile))
    candidates = [name for name, model in catalog.items()
                  if name not in allowed and ":" not in name and not name.startswith(("~", "openrouter/", "perplexity/"))
                  and not any(word in name for word in ("search", "research"))
                  and model.get("output_modalities") == ["text"]
                  and "max_tokens" in model.get("supported_parameters", [])
                  and ("endpoints" not in model or "/api/v1/chat/completions" in model["endpoints"])]
    if len(candidates) < MIN_POOL_SIZE:
        raise ValueError("Cannot verify submission allowlists: the live OpenRouter catalog has too few eligible probe models. Retry later.")
    rng = secrets.SystemRandom()
    chosen = []
    if profile == "reasoning-query-rewriting":
        # Detect accidentally assigning the wider shared profile to the dedicated key.
        boundary = sorted(set(PROFILES["shared"]["generation"]) - allowed)
        available = [name for name in boundary if name in candidates]
        if not available:
            raise ValueError("Cannot verify the reasoning-query-rewriting profile boundary: its probe model is unavailable in the live catalog. Retry later.")
        chosen.append(rng.choice(available))
    while len(chosen) < PROBE_COUNT:
        vendors = {name.split("/", 1)[0] for name in chosen}
        remaining = [name for name in candidates if name not in chosen and name.split("/", 1)[0] not in vendors]
        if not remaining:
            raise ValueError("Cannot verify submission allowlists: insufficient provider diversity in the live model catalog. Retry later.")
        chosen.append(rng.choice(remaining))
    return chosen


def model_access_denied(status, body):
    """Recognize explicit 403/404 model-access denials with unambiguous evidence."""
    if status not in (403, 404) or not isinstance(body, dict):
        return False
    error = body.get("error")
    if not isinstance(error, dict) or error.get("code") != status:
        return False
    metadata = error.get("metadata") or {}
    if not isinstance(metadata, dict) or any(key in metadata for key in (
            "limit_source", "provider_name", "raw", "reasons", "flagged_input", "patterns")):
        return False
    message = error.get("message", "")
    if not isinstance(message, str):
        return False
    message = message.lower()
    if any(word in message for word in ("budget", "credit", "quota", "rate limit", "moderation", "content filter",
                                        "prompt injection", "region", "provider", "disabled key", "invalid key")):
        return False
    if status == 404:
        # Guardrail routing errors must account for every candidate endpoint.
        count = metadata.get("input_endpoint_count")
        reasons = metadata.get("ineligibility_reasons")
        return ("model blocked by guardrail" in message
                and metadata.get("failed_routing_step") == "Filter by Guardrails"
                and type(count) is int and count > 0
                and isinstance(reasons, list) and len(reasons) == 1
                and isinstance(reasons[0], dict)
                and reasons[0].get("reason") == "model-ignored-by-guardrail"
                and type(reasons[0].get("endpoint_count")) is int
                and reasons[0]["endpoint_count"] == count)
    return bool(re.search(r"\bmodels?\b.{0,250}\b(?:not allowed|not permitted|not authorized|not enabled|"
                          r"access denied|access restricted|not in (?:the |your )?(?:allowlist|allowed)|"
                          r"blocked by (?:the |your )?guardrail)", message))


def check_probe(opener, key, profile, model):
    name = PROFILES[profile]["key"]
    payload = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}],
               "max_tokens": 1, "stream": False}
    request = Request(CHAT_URL, data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                               "Accept": "application/json", "User-Agent": "Search-SWE CLI"})
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        status = error.code
        with error:
            raw = error.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, ValueError, HTTPException):
        raise ValueError(f"Cannot verify {name}: network/request failure during the model-access check. "
                         "Check connectivity and key format, then retry; evaluation was not started.") from None
    if 200 <= status < 300:
        raise ValueError(f"Invalid submission allowlist for {name}: OpenRouter accepted out-of-list model {model}. "
                         f"Assign the exact {len(model_ids(profile))}-model profile and retry. Setup: {DOC_URL}")
    try:
        body = json.loads(raw) if len(raw) <= MAX_RESPONSE_BYTES else None
    except (ValueError, UnicodeError):
        body = None
    if model_access_denied(status, body):
        return
    reasons = {400: "invalid request or unsupported parameters", 401: "invalid or disabled API key",
               402: "insufficient credits", 403: "denial not identified as a model-access restriction",
               404: "model restriction not established or routing endpoint unavailable", 429: "rate limit"}
    reason = reasons.get(status, "unexpected provider response")
    raise ValueError(f"Cannot verify {name}: HTTP {status} ({reason}) for {model}. "
                     f"This does not establish a model allowlist; evaluation was not started. "
                     f"Check the key's model guardrail, account status and connectivity, then retry. Setup: {DOC_URL}")


def verify_submission_keys(tasks, env):
    variables = set().union(*(task.variables() for task in tasks))
    profiles = [profile for profile, values in PROFILES.items()
                if values["key"] in variables and env.get(values["key"], "").strip()]
    if not profiles:
        return
    print("Required submission-key check: 3 out-of-list requests per enabled key (max_tokens=1). "
          "Accepted requests may incur minimal API charges.", flush=True)
    catalog, source = load_models(refresh=True)
    if source != "live":
        raise ValueError("Cannot verify submission allowlists: a fresh OpenRouter model catalog is required. "
                         "Check connectivity and retry; evaluation was not started.")
    opener = build_opener(NoRedirect())
    for profile in profiles:
        name = PROFILES[profile]["key"]
        models = probe_models(profile, catalog)
        print(f"Checking {name}: required {len(model_ids(profile))}-model profile...", flush=True)
        for model in models:
            check_probe(opener, env[name], profile, model)
        print(f"{name}: all 3 sampled models were denied by model-access restrictions.", flush=True)
