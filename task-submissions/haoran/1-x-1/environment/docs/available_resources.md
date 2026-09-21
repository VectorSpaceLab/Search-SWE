# Available Resources

The submission may use the generation API below only in its answering component. Memory preparation, index construction and retrieval use local computation.

Harbor injects `OPENROUTER_API_KEY` into the development container at runtime. Read it directly with `$OPENROUTER_API_KEY` or `os.environ["OPENROUTER_API_KEY"]`; do not source a `.env` file inside the container. Only explicitly configured variables are supplied, not the runner's entire environment.

The benchmark runner supplies the credential before starting the task:

```dotenv
OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY>
```

For development self-tests, check that it exists without displaying its value:

```python
import os

if not os.environ.get("OPENROUTER_API_KEY"):
    raise RuntimeError("OPENROUTER_API_KEY is not set")
```

Credentials are runtime resources, not build-time settings. Keep them out of code, memory, indexes, prompts and logs. During evaluation, the answerer uses the transport below and does not receive the real API key.

Harbor limits submission API access to `openrouter.ai`. The coding agent and verifier judges use separate model access, which is not an additional submission resource. Documentation links are references, not additional permitted network destinations.

## Retrieval resources

Use installed libraries and local computation to prepare the memory, build the index and retrieve records. No external embedding, reranking, summarization or other helper API is permitted for these operations, including during development. The model running the coding session is separate from these submission resources.

## Generative LLM resources

Generative calls are allowed only through the OpenRouter API, and only from `answer.sh`. The answerer may choose among these four model IDs:

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507`

This is the complete allowlist. No single answer model is imposed by the verifier; include your selected model ID explicitly in each request. You may select different allowed models across requests within the existing call budget.

Each request must use only the current question and the strings returned by the retriever. The answerer must not read the original transcripts, full memory, index or previous requests, or contain corpus-specific facts in its code or prompts.

OpenRouter generation resources:

- Quickstart: `https://openrouter.ai/docs/quickstart`
- API documentation: `https://openrouter.ai/docs/api/reference/overview`
- OpenAI-compatible endpoint: `https://openrouter.ai/api/v1/chat/completions`

### Evaluation API transport

During evaluation, `answer.sh` receives `TASK_LLM_CLIENT` and `TASK_LLM_FD`. The provided client forwards Chat Completions requests while the verifier retains the real provider credential. Direct network access from the submitted process is disabled.

```python
import importlib.util
import os

spec = importlib.util.spec_from_file_location("task_llm", os.environ["TASK_LLM_CLIENT"])
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
response = api.chat_completion(
    messages=[{"role": "user", "content": prompt_from_current_query_and_retrieved_memories}],
    model="qwen/qwen3.5-9b",  # Example; choose any model from the allowlist.
    temperature=0,
    max_tokens=1000,
)
text = response["choices"][0]["message"]["content"]
```

Preserve the file descriptor named by `TASK_LLM_FD` when starting an answerer subprocess. When `TASK_LLM_CLIENT` is present, use this transport and do not require `OPENROUTER_API_KEY`.

### Development self-tests

The development container provides `OPENROUTER_API_KEY` but no evaluation transport. When `TASK_LLM_CLIENT` is absent, your answerer may send the same request directly to the configured API:

```python
import os
import requests

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
    json=request_body,
    timeout=45,
    allow_redirects=False,
)
response.raise_for_status()
result = response.json()
```

Build `request_body` from the current question and your retriever's output, including an explicit allowed `model`. Run the three submission commands on the public questions using the interfaces in the task instruction; keep development outputs outside `/app`. The same API limits apply in development and evaluation. A failed call does not permit using an unlisted model, provider or endpoint.

### Request limits

Each question permits at most two API calls, with at most 2,000 output tokens per call. Allowed request options are `model`, `messages`, `temperature`, `top_p`, `max_tokens`, and `response_format`. Only the listed request options are accepted by the evaluation transport.

A request may contain 1–32 messages with string `role` and `content` fields; permitted roles are `system`, `user` and `assistant`. The serialized request, including its newline, must fit within 128 KiB. Streaming, tool calls and alternate endpoints are not supported. If the retrieved information is insufficient, answer accordingly rather than seeking other evidence.

### Strict allowlist and jailbreak penalty

The four model IDs above, OpenRouter endpoint and answering-only use are mandatory restrictions, not recommendations. Do not use other providers, external search or answer services, benchmark-answer datasets, or helper APIs for memory preparation or retrieval. Do not reuse information across answering requests.

A prohibited API call, access to unprovided evidence or bypass of the required pipeline is a task violation. If detected by the verifier or trajectory audit, it sets the entire task score to `0`, regardless of retrieval or answer quality.
