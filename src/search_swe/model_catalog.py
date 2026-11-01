"""Public OpenRouter metadata, cached locally and searched without API keys."""

import json
import math
from http.client import HTTPException
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.request import Request, urlopen

from prompt_toolkit.completion import Completer, Completion


CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_SECONDS = 24 * 60 * 60
MAX_BYTES = 10 * 1024 * 1024
MODEL_ID = re.compile(r"~?[a-z0-9][a-z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._:+-]*")


def clean_text(value):
    return "".join(char for char in str(value) if char.isprintable())[:160]


def parse_models(document):
    if not isinstance(document, dict) or not isinstance(document.get("data"), list):
        raise ValueError("Invalid model catalog")
    result = {}
    for row in document["data"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not MODEL_ID.fullmatch(row["id"]):
            continue
        model = {"id": row["id"], "name": clean_text(row.get("name") or row["id"])}
        for key in ("supported_parameters", "endpoints"):
            if isinstance(row.get(key), list) and all(isinstance(value, str) for value in row[key]):
                model[key] = row[key]
        architecture = row.get("architecture")
        if isinstance(architecture, dict):
            for key in ("input_modalities", "output_modalities"):
                if isinstance(architecture.get(key), list):
                    model[key] = architecture[key]
        if isinstance(row.get("context_length"), int) and row["context_length"] > 0:
            model["context_length"] = row["context_length"]
        top = row.get("top_provider") or {}
        if isinstance(top, dict) and isinstance(top.get("max_completion_tokens"), int) and top["max_completion_tokens"] > 0:
            model["max_output_tokens"] = top["max_completion_tokens"]
        pricing = row.get("pricing") or {}
        if isinstance(pricing, dict) and "prompt" in pricing and "completion" in pricing:
            cost = {}
            for target, source in (("input", "prompt"), ("output", "completion"),
                                   ("cacheRead", "input_cache_read"), ("cacheWrite", "input_cache_write")):
                try:
                    value = float(pricing.get(source, 0)) * 1_000_000
                    if math.isfinite(value) and value >= 0:
                        cost[target] = value
                except (TypeError, ValueError):
                    pass
            if len(cost) == 4:
                model["cost"] = cost
        result[model["id"]] = model
    if not result:
        raise ValueError("Empty model catalog")
    return result


def load_models(*, offline=False, refresh=False, cache=None):
    """Return (models, source). Catalog failure always leaves manual input usable."""
    cache = cache or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "search-swe/openrouter-models.json"
    cached, fetched = {}, 0
    try:
        if cache.stat().st_size <= MAX_BYTES:
            document = json.loads(cache.read_text())
            cached = parse_models(document)
            fetched = float(document.get("fetched_at", 0))
    except (OSError, ValueError, TypeError):
        pass
    if cached and not refresh and 0 <= time.time() - fetched < CACHE_SECONDS:
        return cached, "cache"
    if not offline:
        try:
            request = Request(CATALOG_URL, headers={"Accept": "application/json", "User-Agent": "Search-SWE CLI"})
            with urlopen(request, timeout=8) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError("Model catalog exceeds size limit")
            document = json.loads(payload)
            models = parse_models(document)
            document["fetched_at"] = time.time()
        except (OSError, ValueError, TypeError, HTTPException):
            pass
        else:
            temporary = None
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", dir=cache.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(document, stream)
                os.replace(temporary, cache)
            except OSError:
                pass  # A read-only cache does not prevent model selection.
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return models, "live"
    return cached, "stale cache" if cached else "unavailable"


def eligible(model, agent):
    if "output_modalities" in model and "text" not in model["output_modalities"]:
        return False
    if "supported_parameters" in model and "tools" not in model["supported_parameters"]:
        return False
    endpoint = {"claude-code": "/api/v1/messages", "pi": "/api/v1/chat/completions", "codex": "/api/v1/responses"}[agent]
    return "endpoints" not in model or endpoint in model["endpoints"]


class ModelCompleter(Completer):
    def __init__(self, models, preferred=""):
        self.models = sorted(models.values(), key=lambda model: (model["id"] != preferred, model["id"]))

    def get_completions(self, document, complete_event):
        query = document.text_before_cursor
        tokens = re.findall(r"\w+", query.casefold())
        for model in self.models:
            searchable = f"{model['id']} {model['name']}".casefold()
            if not all(token in searchable for token in tokens):
                continue
            context = model.get("context_length")
            yield Completion(model["id"], start_position=-len(query),
                             display=f"{model['id']} · {model['name']}",
                             display_meta=f"{context:,} tokens" if context else "")
