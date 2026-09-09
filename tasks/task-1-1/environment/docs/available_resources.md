# Available Resources

The submission may use the external APIs below for retrieval and, where allowed by the task instruction, generative LLM calls.

The variables listed below are injected by Harbor at runtime and are available directly in the agent container's process environment, including child processes started by the agent. Read them as ordinary environment variables; for example, use `$OPENROUTER_API_KEY` in shell or `os.environ["OPENROUTER_API_KEY"]` in Python. Do not source a `.env` file inside the container. Only variables listed in this document and configured by Harbor are guaranteed to be available. Do not assume that all variables from a `.env` file are automatically injected.

For example, check whether a credential is present without exposing its value:

```bash
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "OPENROUTER_API_KEY is not set" >&2
    exit 1
fi
```

```python
import os

if not os.environ.get("OPENROUTER_API_KEY"):
    raise RuntimeError("OPENROUTER_API_KEY is not set")
```

These credentials are runtime resources. Do not hard-code them, print or log their values, write them into source code, indexes, or output artifacts, or assume that they are available during Docker image build.

```bash
OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY>
JINA_API_KEY=<YOUR_JINA_API_KEY>
```

## Retrieval resources

Embedding and reranking models may be used through OpenRouter or Jina. Use the exact model IDs and request formats supported by the selected provider. These endpoints are for retrieval operations such as embedding, candidate scoring, and reranking; do not use them as a general-purpose answer generation service.

OpenRouter:

- Quickstart: `https://openrouter.ai/docs/quickstart`
- API documentation: `https://openrouter.ai/docs/api_reference/overview`
- Embedding models: `https://openrouter.ai/models?output_modalities=embeddings`
- Reranking models: `https://openrouter.ai/models?output_modalities=rerank`

Jina:

- Quickstart: `https://docs.jina.ai/get-started/quickstart`
- Embedding API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/embeddings`
- Reranking API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/rerank`
- Models: `https://jina.ai/models`

## Generative LLM resources

Generative calls are allowed only through the OpenRouter API. The following four model IDs are the complete allowlist:

- `qwen/qwen3.6-35b-a3b` — `https://openrouter.ai/qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b` — `https://openrouter.ai/qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b` — `https://openrouter.ai/qwen/qwen3.5-9b`

OpenRouter generation resources:

- Quickstart: `https://openrouter.ai/docs/quickstart`
- API documentation: `https://openrouter.ai/docs/api_reference/overview`
- OpenAI-compatible endpoint: `https://openrouter.ai/api/v1/chat/completions`

### Strict allowlist and jailbreak penalty

The four Qwen IDs above are an allowlist, not a recommendation. Do not call any other generative model ID, any other generative provider, or a prohibited chat/completions endpoint. In particular, do not use other provider's generative endpoint, and do not use an embedding or reranking endpoint as a substitute for generation.

If the verifier or trajectory audit detects a prohibited generative model or provider call, the submission is classified as jailbreak and the entire task receives a score of `0`, regardless of retrieval quality or final answer quality.
