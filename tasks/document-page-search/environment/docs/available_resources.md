# Available Resources

Use the supplied page collection, local models and installed runtime. Optional retrieval and generation APIs are listed below.

## Local resources

- `/task/data/corpus/`: page records, page images and supplied Markdown transcriptions.
- `/task/data/validation/queries.jsonl`: public development questions.
- `/task/data/validation/labels.jsonl`: public page-relevance labels.
- `/task/models/page-encoder/` and `/task/models/vision-backbone/`: read-only ColQwen2.5 weights, processor and tokenizer. The adapter configuration refers to the supplied backbone directory.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Retrieval resources

Embedding and reranking models may be used through OpenRouter or Jina. Use the exact model IDs and request formats supported by the selected provider. These endpoints are for retrieval operations such as embedding, candidate scoring, and reranking; do not use them as a general-purpose answer generation service.

OpenRouter:

- API documentation: `https://openrouter.ai/docs/api_reference/overview`
- Embedding models: `https://openrouter.ai/models?output_modalities=embeddings`
- Reranking models: `https://openrouter.ai/models?output_modalities=rerank`

Jina:

- Embedding API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/embeddings`
- Reranking API documentation: `https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/rerank`
- Models: `https://jina.ai/models`

## Generative LLM resources

Generative calls may use only the OpenRouter Chat Completions endpoint and the following model IDs. This is the complete generation allowlist:

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507`

OpenRouter API:

- OpenAI-compatible endpoint: `https://openrouter.ai/api/v1/chat/completions`
- PDF OCR / multimodal PDF API guide: `https://openrouter.ai/docs/guides/overview/multimodal/pdfs`

## Network and resource restrictions

The following runtime variables are supplied through the process environment when configured:

- `OPENROUTER_API_KEY`: permitted OpenRouter calls.
- `JINA_API_KEY`: Jina embedding and reranking calls.

Read credentials from the process environment; do not source a `.env` file or place credential values in code, indexes, outputs or logs.

Submission network access is limited to `openrouter.ai` and `api.jina.ai`. Documentation links do not authorize access to additional hosts. Use the APIs only for operations permitted by the task instruction.

Only the listed generative model IDs and the OpenRouter Chat Completions endpoint are permitted. Other generative models, providers and endpoints are prohibited. Embedding and reranking endpoints must not be used as substitutes for generation. If the verifier or trajectory audit detects a prohibited generative call, the submission is classified as a jailbreak and the entire task receives a score of `0`.
