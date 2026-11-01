"""Fixed OpenRouter submission-key allowlists, checked on 2026-11-01.

These benchmark profiles are independent of the live coding-agent model catalog.
See docs/evaluation/submission-models.md for sources and key setup.
"""

GUARDRAIL_URL = "https://openrouter.ai/docs/guides/features/guardrails"
DOC_URL = "https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/submission-models.md"
EXCLUDED_MODEL = "qwen/qwen3-reranker-8b"

PROFILES = {
    "shared": {
        "key": "OPENROUTER_API_KEY",
        "generation": [
            "qwen/qwen3.5-35b-a3b",
            "qwen/qwen3.6-35b-a3b",
            "qwen/qwen3.5-9b",
            "qwen/qwen3-30b-a3b-instruct-2507",
        ],
        "embedding": [
            "qwen/qwen3-embedding-8b",
            "qwen/qwen3-embedding-4b",
            "openai/text-embedding-3-small",
            "openai/text-embedding-3-large",
            "openai/text-embedding-3-large:batch",
            "mistralai/codestral-embed-2505",
            "openai/text-embedding-ada-002",
            "openai/text-embedding-ada-002:batch",
            "google/gemini-embedding-001",
            "mistralai/mistral-embed-2312",
            "sentence-transformers/all-minilm-l6-v2",
            "sentence-transformers/all-mpnet-base-v2",
            "baai/bge-m3",
            "baai/bge-large-en-v1.5",
            "sentence-transformers/multi-qa-mpnet-base-dot-v1",
            "baai/bge-base-en-v1.5",
            "sentence-transformers/all-minilm-l12-v2",
            "sentence-transformers/paraphrase-minilm-l6-v2",
            "intfloat/multilingual-e5-large",
            "intfloat/e5-base-v2",
            "intfloat/e5-large-v2",
            "thenlper/gte-large",
            "thenlper/gte-base",
            "nvidia/llama-nemotron-embed-vl-1b-v2:free",
            "perplexity/pplx-embed-v1-0.6b",
            "perplexity/pplx-embed-v1-4b",
            "google/gemini-embedding-2-preview",
            "google/gemini-embedding-2",
            "nvidia/nemotron-3-embed-1b:free",
            "voyageai/voyage-4-large",
            "voyageai/voyage-4",
            "voyageai/voyage-4-lite",
            "voyageai/voyage-multimodal-3.5",
            "voyageai/voyage-code-4",
            "liquid/lfm-2.5-embedding-350m:free",
        ],
        "rerank": [
            "voyageai/rerank-2.5-lite",
            "voyageai/rerank-2.5",
            "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
            "cohere/rerank-v3.5",
            "cohere/rerank-4-fast",
            "cohere/rerank-4-pro",
            "voyageai/rerank-3-lite",
            "voyageai/rerank-3",
        ],
    },
    "reasoning-query-rewriting": {
        "key": "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY",
        "generation": [
            "qwen/qwen3.6-35b-a3b",
            "qwen/qwen3.5-35b-a3b",
            "qwen/qwen3.5-9b",
        ],
        "embedding": [
            "qwen/qwen3-embedding-8b",
            "qwen/qwen3-embedding-4b",
            "voyageai/voyage-4-large",
            "voyageai/voyage-4",
            "voyageai/voyage-4-lite",
            "google/gemini-embedding-001",
            "openai/text-embedding-3-large",
            "openai/text-embedding-3-small",
            "baai/bge-m3",
        ],
        "rerank": [
            "voyageai/rerank-2.5",
            "voyageai/rerank-2.5-lite",
            "cohere/rerank-4-pro",
            "cohere/rerank-4-fast",
            "cohere/rerank-v3.5",
        ],
    },
}


def model_ids(profile):
    return [model for kind in ("generation", "embedding", "rerank") for model in PROFILES[profile][kind]]


def profile_for_key(name):
    return next((profile for profile, values in PROFILES.items() if values["key"] == name), None)


def policy_summary(profile):
    values = PROFILES[profile]
    return {"profile": profile, "key": values["key"], "model_count": len(model_ids(profile)),
            "counts": {kind: len(values[kind]) for kind in ("generation", "embedding", "rerank")},
            "excluded_models": [EXCLUDED_MODEL],
            "required_when_enabled": True,
            "validation": "3 out-of-list model-access checks before saving configuration or starting a run",
            "show_command": f"search-swe submission-models --profile {profile}",
            "setup_url": GUARDRAIL_URL}


def setup_hint(profile):
    info = policy_summary(profile)
    counts = info["counts"]
    return (f"{info['key']}: REQUIRED fixed {info['model_count']}-model {profile} allowlist "
            f"({counts['generation']} generation, {counts['embedding']} embedding, {counts['rerank']} rerank).\n"
            f"{EXCLUDED_MODEL} is excluded for cost. Coding-agent and judge keys use their own model access.\n"
            f"Full IDs: {info['show_command']} (add --json to export allowed_models).\n"
            f"Create and assign a key-specific guardrail: {GUARDRAIL_URL}\n"
            "The CLI checks 3 out-of-list models (max_tokens=1); incorrect or unverifiable restrictions block the run.")


def display_profile(profile):
    print(setup_hint(profile))
    print("Use this fixed list together with each task's resource policy. Provider permissions are configured in OpenRouter.")
    print(f"Setup guide: {DOC_URL}")
    for kind in ("generation", "embedding", "rerank"):
        print(f"\n{kind.capitalize()} ({len(PROFILES[profile][kind])}):")
        for model in PROFILES[profile][kind]:
            print(model)
