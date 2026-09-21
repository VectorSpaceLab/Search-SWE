# Available Resources

The submission may use the generation API below only in its answering component. Memory preparation, index construction and retrieval use local computation.

Harbor injects `OPENROUTER_API_KEY` into the development container at runtime. Read it directly with `$OPENROUTER_API_KEY` or `os.environ["OPENROUTER_API_KEY"]`; do not source a `.env` file inside the container. Only explicitly configured variables are supplied, not the runner's entire environment.

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

Credentials are runtime resources, not build-time settings. Keep them out of code, memory, indexes, prompts and logs. During evaluation, the answerer uses the transport documented in the task instruction and does not receive the real API key.

Harbor limits submission API access to `openrouter.ai`. The coding agent and verifier judges use separate model access, which is not an additional submission resource. Documentation links are references, not additional permitted network destinations.

```dotenv
OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY>
```

## Retrieval resources

Use installed libraries and local computation to prepare the memory, build the index and retrieve records. No external embedding, reranking, summarization or other helper API is permitted for these operations, including during development. The model running the coding session is separate from these submission resources.

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

The four model IDs above, OpenRouter endpoint and answering-only use are mandatory restrictions, not recommendations. Do not use other providers, external search or answer services, benchmark-answer datasets, or helper APIs for memory preparation or retrieval. Do not reuse information across answering requests.

A prohibited API call, access to unprovided evidence or bypass of the required pipeline is a task violation. If detected by the verifier or trajectory audit, it sets the entire task score to `0`, regardless of retrieval or answer quality.
