# Available Resources

## Answering API configuration

Read the following runtime environment variables when implementing and testing your answerer:

| Variable | Meaning |
| --- | --- |
| `ANSWER_API_KEY` | Credential for the answering API |
| `ANSWER_API_BASE_URL` | OpenAI-compatible API base URL; the chat endpoint is this URL plus `/chat/completions` |
| `ANSWER_MODEL` | The only model your answerer may call |

Harbor injects these values into the development environment and the answering process at runtime. Read them as environment variables; do not source a `.env` file inside the container or hard-code a key, URL, or model. Check that the variables are set without printing the key:

```python
import os
for name in ("ANSWER_API_KEY", "ANSWER_API_BASE_URL", "ANSWER_MODEL"):
    if not os.environ.get(name):
        raise RuntimeError(f"Missing runtime setting: {name}")
```

Only the configured endpoint and model are allowed. Do not use other providers, external search or answer services, or benchmark-answer datasets. Credentials must not be written into submitted code, memory, indexes, prompts, or logs. The model running your coding session is separate from this API resource.

## Permitted API use

Only the answerer may call the configured API, using the current question and the records returned by the submitted retriever. This restriction applies during development and evaluation. Do not call helper APIs for memory construction, interpretation of the raw corpus, summarization, indexing, embedding or ranking. Local computation and installed libraries are allowed.

The allowed API host is `api.deepseek.com`. Use only the endpoint and model named by the injected settings. The coding agent's model access and verifier judge credentials are separate resources.

At evaluation time, retrieval has no network access or API credentials. The answerer can read only its corpus-independent code, runtime dependencies and the current question's retrieved records. The original history, full memory and previous requests are unavailable to it.

## Calling the API from your answerer

Use the task-provided Chat Completions transport in your submitted answerer. It forwards your request to `ANSWER_API_BASE_URL` using `ANSWER_API_KEY`; you supply the prompts and parse the response. Direct network access is disabled during evaluation, so this transport is the permitted API route.

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

During evaluation, the runtime supplies `TASK_LLM_CLIENT` and `TASK_LLM_FD` to `answer.sh`. Preserve `TASK_LLM_FD` if launching another process to implement the answerer. The API key and base URL remain available under the configuration names above; the retrieval process does not receive them.

### Development self-tests

The development environment supplies `ANSWER_API_KEY`, `ANSWER_API_BASE_URL`, and `ANSWER_MODEL`, but no verifier transport descriptor. Your answerer should use the transport above when `TASK_LLM_CLIENT` is present. Otherwise, during development only, it may send the same request directly to the configured endpoint:

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

`request_body` is your answerer's Chat Completions request, built only from the current question and the retriever's output. Use the same call and token limits in both modes. The direct route is unavailable during evaluation; do not fall back to another endpoint or model when a call fails.

Run your retriever on a public question, then pass that exact output file to your answerer using the two interfaces in the task instruction. Keep test outputs outside `/app`.

Allowed request options are `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `response_format`, and `thinking`. Each request may contain 1–32 messages, each with string `role` and `content` fields; roles are `system`, `user`, or `assistant`. Serialized requests must fit within 128 KiB including the newline. Each question permits up to two API calls and each call up to 2,000 output tokens. Streaming, tool calls, and alternate endpoints are unsupported. Provider-specific options should be used only if supported by the configured endpoint.

The answerer must use only the current query and retrieved evidence. Its prompts and static dependencies must not contain corpus-specific facts. Do not reuse information from previous questions. When the evidence is insufficient, say so in plain text.

Using an API outside the answering component, accessing unprovided evidence, or otherwise bypassing the memory and retrieval pipeline is a task violation and sets the entire score to zero.
