# Available Resources

API use is optional. Use only the resources below for their permitted purposes.

Read the runtime-provided environment variables `OPENROUTER_API_KEY` for OpenRouter and `JINA_API_KEY` for Jina. Do not rely on a container `.env` file or on credentials during image build. Never hard-code, print, log or store their values in source code, container images, indexes or output artifacts.

Network access is limited to `openrouter.ai` and `api.jina.ai`. Documentation links do not authorize additional hosts. The coding agent's own model connection is not a submission resource.

## Local resources

Local multilingual E5-small weights, tokenizer and configuration are read-only at `/task/models/encoder/`.

## Retrieval resources

OpenRouter and Jina embedding and reranking APIs may be used for retrieval operations such as embedding, candidate scoring and reranking. Use the selected provider's exact model IDs and request formats; these endpoints must not be used for generation.

- OpenRouter: [API documentation](https://openrouter.ai/docs/api_reference/overview), [embedding models](https://openrouter.ai/models?output_modalities=embeddings), [reranking models](https://openrouter.ai/models?output_modalities=rerank).
- Jina: [embedding API](https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/embeddings), [reranking API](https://api.jina.ai/scalar#tag/search-foundation-models/POST/v1/rerank), [models](https://jina.ai/models).

## Generative LLM resources

Use generation only for the retrieval or query-transformation roles permitted by the task instruction.

Generation is allowed only through OpenRouter at `https://openrouter.ai/api/v1/chat/completions`, using one of these exact model IDs:

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`
- `qwen/qwen3-30b-a3b-instruct-2507`

This is the complete allowlist. A prohibited generative model, provider or endpoint call is an integrity violation and makes the entire task score zero, regardless of retrieval or answer quality.

## Local representations
ASR confidences are geometric means of generated-token conditional probabilities. They describe the fixed recognizer's own output probabilities and are not calibrated probabilities that words are correct. Word spans refer to the corresponding hypothesis string. All alternatives come from the same fixed five-beam recognizer; no clean question or relevance label was used in their decoding. Only the listed text/retrieval/generative resources are available. Do not call a speech-recognition service, obtain clean evaluation queries, or use an external answer/search service.
