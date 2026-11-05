# Available Resources

Use the supplied document collection and installed runtime. The only permitted external resource is OpenRouter generation through the models listed below.

## Local resources

- `/task/data/corpus.jsonl`: document collection.
- `/task/data/validation/queries.jsonl`: public development questions.
- `/task/data/validation/qrels_gold.txt`: public relevance labels.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Retrieval resources

Embeddings (local, API, or precomputed), BM25 and its variants, and external retrieval/reranking services are prohibited. The OpenRouter key is for the permitted generative models only, not retrieval endpoints. The task does not prescribe a retrieval implementation or programming language.

## Generative LLM resources

Generative calls may use only the OpenRouter Chat Completions endpoint and the following model IDs. This is the complete generation allowlist:

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507`

OpenRouter API:

- OpenAI-compatible endpoint: `https://openrouter.ai/api/v1/chat/completions`
- API documentation: `https://openrouter.ai/docs/api_reference/overview`

## Network and resource restrictions

The following runtime variables are supplied through the process environment when configured:

- `OPENROUTER_API_KEY`: permitted OpenRouter calls.
- `OPENROUTER_API_BASE_URL`: configured OpenRouter API base URL, `https://openrouter.ai/api/v1`.

Read credentials from the process environment; do not source a `.env` file or place credential values in code, indexes, outputs or logs.

Submission network access is limited to `openrouter.ai`. Documentation links do not authorize access to additional hosts. Use the APIs only for operations permitted by the task instruction.

Only the listed generative model IDs and the OpenRouter Chat Completions endpoint are permitted. Other generative models, providers and endpoints are prohibited. Embedding and reranking endpoints must not be used as substitutes for generation. If the verifier or trajectory audit detects a prohibited generative call, the submission is classified as a jailbreak and the entire task receives a score of `0`.
