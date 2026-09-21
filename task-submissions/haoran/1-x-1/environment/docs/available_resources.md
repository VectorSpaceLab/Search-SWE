# Available Resources

The submission may use the generation API below only in its answering component. Memory preparation, index construction and retrieval use local computation.

Harbor supplies the following environment variables during development. Read them directly with shell variables or `os.environ`; do not source a `.env` file inside the container. Only the variables explicitly configured for the task are supplied, not the runner's entire environment.

| Variable | Meaning |
| --- | --- |
| `ANSWER_API_KEY` | Credential for the answering API |
| `ANSWER_API_BASE_URL` | OpenAI-compatible base URL; append `/chat/completions` for chat requests |
| `ANSWER_MODEL` | The exact model ID permitted for the answerer |

The benchmark runner fills in these settings before starting the task:

```dotenv
ANSWER_API_KEY=<YOUR_ANSWER_API_KEY>
ANSWER_API_BASE_URL=<YOUR_ANSWER_API_BASE_URL>
ANSWER_MODEL=<YOUR_ANSWER_MODEL>
```

For development self-tests, check that the settings exist without displaying their values:

```python
import os

for name in ("ANSWER_API_KEY", "ANSWER_API_BASE_URL", "ANSWER_MODEL"):
    if not os.environ.get(name):
        raise RuntimeError(f"Missing runtime setting: {name}")
```

Credentials are supplied at runtime, not during image build. Keep them out of code, memory, indexes, prompts and logs. During evaluation, submitted programs do not receive the real API key or base URL; the answerer uses the transport described below.

Harbor limits task API access to `api.deepseek.com`. The official launcher separately allows the coding agent's model host when needed. Coding-agent and judge access does not authorize additional services for the submission. Documentation links are references, not additional permitted network destinations.

## Retrieval resources

Use installed libraries and local computation to prepare the memory, build the index and retrieve records. No external embedding, reranking, summarization or other helper API is permitted for these operations, including during development. The model running the coding session is separate from these submission resources.

## Generative LLM resources

Only `answer.sh` may call the configured DeepSeek API. Each request must use only the current question and the strings returned by the retriever. The answerer must not read the original transcripts, full memory, index or previous requests, or contain corpus-specific facts in its code or prompts.

The complete model allowlist is the single exact ID supplied in `ANSWER_MODEL`. Read that value at runtime; do not select another model from the provider's catalog. Read the configured base URL rather than hard-coding an endpoint.

DeepSeek generation resources:

- Quickstart and API documentation: [DeepSeek API Docs](https://api-docs.deepseek.com/).
- API host: `api.deepseek.com`.
- Chat endpoint: `ANSWER_API_BASE_URL` with trailing slashes removed, followed by `/chat/completions`.

### Evaluation API transport

During evaluation, `answer.sh` receives `ANSWER_MODEL`, `TASK_LLM_CLIENT` and `TASK_LLM_FD`. The provided client forwards Chat Completions requests while the verifier retains the real provider credential. Direct network access from the submitted process is disabled.

```python
import importlib.util
import os

spec = importlib.util.spec_from_file_location("task_llm", os.environ["TASK_LLM_CLIENT"])
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
response = api.chat_completion(
    messages=[{"role": "user", "content": prompt_from_current_query_and_retrieved_memories}],
    model=os.environ["ANSWER_MODEL"],
    temperature=0,
    max_tokens=1000,
)
text = response["choices"][0]["message"]["content"]
```

Preserve the file descriptor named by `TASK_LLM_FD` when starting an answerer subprocess. When `TASK_LLM_CLIENT` is present, use this transport and do not require `ANSWER_API_KEY` or `ANSWER_API_BASE_URL`.

### Development self-tests

The development container provides the three `ANSWER_*` variables but no evaluation transport. When `TASK_LLM_CLIENT` is absent, your answerer may send the same request directly to the configured API:

```python
import requests

response = requests.post(
    os.environ["ANSWER_API_BASE_URL"].rstrip("/") + "/chat/completions",
    headers={"Authorization": "Bearer " + os.environ["ANSWER_API_KEY"]},
    json=dict(request_body, model=os.environ["ANSWER_MODEL"]),
    timeout=45,
    allow_redirects=False,
)
response.raise_for_status()
result = response.json()
```

Build `request_body` from the current question and your retriever's output. Run the three submission commands on the public questions using the interfaces in the task instruction; keep development outputs outside `/app`. The same API limits apply in development and evaluation. A failed call does not permit switching providers, models or endpoints.

### Request limits

Each question permits at most two API calls, with at most 2,000 output tokens per call. Allowed request options are `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `response_format` and `thinking`. Use provider-specific options only when the configured endpoint supports them.

A request may contain 1–32 messages with string `role` and `content` fields; permitted roles are `system`, `user` and `assistant`. The serialized request, including its newline, must fit within 128 KiB. Streaming, tool calls and alternate endpoints are not supported. If the retrieved information is insufficient, answer accordingly rather than seeking other evidence.

### Strict allowlist and jailbreak penalty

The configured host, endpoint, model and answering-only use are mandatory restrictions. Do not use other providers, external search or answer services, benchmark-answer datasets, or helper APIs for memory preparation or retrieval. Do not reuse information across answering requests.

A prohibited API call, access to unprovided evidence or bypass of the required pipeline is a task violation. If detected by the verifier or trajectory audit, it sets the entire task score to `0`, regardless of retrieval or answer quality.
