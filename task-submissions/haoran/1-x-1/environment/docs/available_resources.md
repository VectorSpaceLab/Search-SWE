# Available Resources

The submission may use Jina embedding and reranking APIs for memory preparation, index construction and retrieval, and the OpenRouter generation API only in its answering component.

Harbor injects `OPENROUTER_API_KEY` and `JINA_API_KEY` into the development container at runtime. Read them as ordinary environment variables, for example `$OPENROUTER_API_KEY` or `os.environ["JINA_API_KEY"]`; do not source a `.env` file inside the container. Only explicitly configured variables are supplied, not the runner's entire environment.

For development self-tests, check that the credential exists without displaying its value:

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

Credentials are runtime resources, not build-time settings. Keep them out of code, memory, indexes, prompts and logs. During evaluation, build and search use the Jina transport and the answerer uses the OpenRouter transport documented in the task instruction. Submitted processes do not receive real provider keys.

Harbor limits submission API access to `openrouter.ai` and `api.jina.ai`. The coding agent and verifier judges use separate model access, which is not an additional submission resource. Documentation links are references, not additional permitted network destinations.

```dotenv
OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY>
JINA_API_KEY=<YOUR_JINA_API_KEY>
```

## Retrieval resources

Embedding and reranking models may be used through Jina during memory preparation, index construction and retrieval. Use the exact model IDs and request formats supported by Jina. These endpoints are for text embedding, candidate scoring and reranking; do not use them for generation, external search or answer lookup. OpenRouter embedding and reranking endpoints are not provided for this task. Local computation remains available without Jina calls.

Jina:

- Quickstart: `https://docs.jina.ai/get-started/quickstart`
- Embedding API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/embeddings`
- Reranking API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/rerank`
- Models: `https://jina.ai/models`

Use `JINA_API_KEY` for development calls to `https://api.jina.ai/v1/embeddings` or `https://api.jina.ai/v1/rerank`. Evaluation provides the same endpoints through the task transport. Select a model supported by the corresponding Jina endpoint; this task does not fix a single retrieval model. Text inputs are supported; fetching URLs, images or external documents is not permitted. The model running the coding session is separate from these submission resources.

## Generative LLM resources

Generative calls are allowed only through the OpenRouter API, and only from `answer.sh`, using the current question and retrieved strings. The following four model IDs are the complete allowlist:

- `qwen/qwen3.6-35b-a3b` — `https://openrouter.ai/qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b` — `https://openrouter.ai/qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b` — `https://openrouter.ai/qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507` — `https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507`

The fourth model ID is the OpenRouter identifier for `Qwen3-30B-A3B-Instruct-2507`. Include your selected model ID in each request; the verifier does not impose a single answer model. Different allowed models may be selected within the task's call budget.

OpenRouter generation resources:

- Quickstart: `https://openrouter.ai/docs/quickstart`
- API documentation: `https://openrouter.ai/docs/api/reference/overview`
- OpenAI-compatible endpoint: `https://openrouter.ai/api/v1/chat/completions`

### Strict allowlist and jailbreak penalty

The four model IDs above, OpenRouter endpoint and answering-only use are mandatory restrictions, not recommendations. Do not use other providers, external search or answer services, benchmark-answer datasets, or generative APIs for memory preparation or retrieval. Only the Jina embedding and reranking endpoints above are permitted retrieval APIs. Do not reuse information across answering requests.

A prohibited API call, access to unprovided evidence or bypass of the required pipeline is a task violation. If detected by the verifier or trajectory audit, it sets the entire task score to `0`, regardless of retrieval or answer quality.
