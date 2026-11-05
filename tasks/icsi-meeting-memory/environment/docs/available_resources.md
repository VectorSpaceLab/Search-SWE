# Available Resources

Use the supplied meeting history and public validation examples. No local model weights are supplied. Task API access is limited to `openrouter.ai` and `api.jina.ai`; documentation links do not grant access to additional hosts. External search, reader services, answer lookup and benchmark-answer datasets are prohibited.

Development processes receive `OPENROUTER_API_KEY` and, when configured, `JINA_API_KEY` as environment variables. Do not expose or save credentials in code, memories, indexes, prompts, logs or output artifacts. During evaluation, submitted programs use the stage-specific clients below instead of provider keys and have no direct network access.

## Retrieval resources

Local computation and Jina text embedding and reranking are permitted for memory preparation, index construction and retrieval. Generative APIs are not permitted for these operations. Jina is optional; no single retrieval model is prescribed. OpenRouter embedding and reranking endpoints are not supplied for this task.

- Embedding endpoint: `https://api.jina.ai/v1/embeddings` — [API reference](https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/embeddings)
- Reranking endpoint: `https://api.jina.ai/v1/rerank` — [API reference](https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/rerank)
- Supported models: `https://jina.ai/models`

During development, call these endpoints using `JINA_API_KEY`. Use text from the supplied history and select a model supported by the corresponding endpoint. During evaluation, `build.sh` and `run.sh` receive `TASK_JINA_CLIENT` and `TASK_JINA_FD`:

```python
import importlib.util
import os

spec = importlib.util.spec_from_file_location("task_jina", os.environ["TASK_JINA_CLIENT"])
jina = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jina)
vectors = jina.embeddings(model=embedding_model_id, input=text_batch)
ranking = jina.rerank(model=reranker_model_id, query=question, documents=candidate_texts)
```

The client forwards an operation (`embeddings` or `rerank`) and the provider request body through the supplied file descriptor. Preserve `TASK_JINA_FD` when starting subprocesses. Each serialized request, including its newline, must fit within 128 KiB; batch larger inputs. There is no separate Jina call-count limit, but calls count toward the build or retrieval time budget. Use only the current stage's permitted inputs. The answerer does not receive this transport.

## Generative LLM resources

Only `answer.sh` may call a generative model, using the current question and retrieved strings. Generation is allowed through OpenRouter with these four exact model IDs:

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507`

The endpoint is `https://openrouter.ai/api/v1/chat/completions`; see the [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview). Include an allowed model ID in each request. Different allowed models may be selected within the question's call budget.

During development, send Chat Completions requests directly to that endpoint using `OPENROUTER_API_KEY`. During evaluation, `answer.sh` receives `TASK_LLM_CLIENT` and `TASK_LLM_FD`; use this client without requiring a provider key or direct network access:

```python
import importlib.util
import os

spec = importlib.util.spec_from_file_location("task_llm", os.environ["TASK_LLM_CLIENT"])
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
response = api.chat_completion(
    messages=[{"role": "user", "content": prompt_from_current_question_and_retrieved_notes}],
    model="qwen/qwen3.5-9b",
    temperature=0,
    max_tokens=1000,
)
text = response["choices"][0]["message"]["content"]
```

Preserve `TASK_LLM_FD` when starting subprocesses. The answerer must not consult the full memory, index, original transcripts, previous requests or corpus-specific facts embedded in its code.

Each question permits at most two generation calls, each requesting 1–2,000 output tokens. Accepted options are `model`, `messages`, `temperature`, `top_p`, `max_tokens` and `response_format`. Messages must be a list of 1–32 objects with exactly the string fields `role` and `content`; allowed roles are `system`, `user` and `assistant`. Each serialized request, including its newline, must fit within 128 KiB. Streaming, tool calls and alternate endpoints are not supported. The same call and content restrictions apply to development self-tests.

Do not use unlisted models, providers or endpoints, or use retrieval endpoints as generation substitutes. A failed call does not authorize a different service. Prohibited API calls, hidden-data access or bypassing the required pipeline cause the entire task to receive zero. See the task instruction for the submission interfaces, stage inputs and execution limits.
