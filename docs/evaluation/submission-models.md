# OpenRouter submission-key model allowlists

[Documentation index](../README.md)

**Every enabled OpenRouter submission key must use its exact model profile:**

| Host variable | Profile | Generation | Embedding | Rerank | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| `OPENROUTER_API_KEY` | Shared | 4 | 35 | 8 | **47** |
| `REASONING_QUERY_REWRITING_OPENROUTER_API_KEY` | Reasoning query rewriting | 3 | 9 | 5 | **17** |

The profiles allow a few lightweight generation models and a broad selection of
embeddings/rerankers. **Both exclude `qwen/qwen3-reranker-8b` for cost.** These are
fixed benchmark lists; task resource documents may further restrict their use.

These keys serve submitted search programs. Coding-agent
`AGENT_OPENROUTER_API_KEY` and judge keys need separate model access. Jina uses
its own `JINA_API_KEY`.

## Configure the keys

1. Create a shared submission key and, if enabling OpenRouter resources for
   reasoning-query-rewriting, a separate key for its 17-model profile.
2. In OpenRouter **Guardrails**, create the exact **Allowed Models** list below,
   save it, and assign it to the matching key under **API Keys**. An empty list
   allows all models. Check the effective restrictions after assignment.
3. Enter the key with `search-swe configure TASK`, or set its host variable in
   your ignored `.env`. Use `--edit-credentials` to replace an existing key.

Assign guardrails directly to submission keys so coding-agent and judge keys
retain their required access. See [OpenRouter's setup guide](https://openrouter.ai/docs/guides/features/guardrails).

## Required CLI checks

Before saving configuration or starting a batch, the CLI checks enabled
submission keys used by the selected tasks, including previously saved keys.
Each key receives three distinct out-of-list Chat Completions requests with
`max_tokens=1`; accepted requests may incur small charges.

Candidates are randomly drawn across vendors from a fresh catalog with at least
25 eligible models. Reasoning-query-rewriting also probes the shared-only Qwen
generation model to detect an incorrectly assigned wider profile.

**All three requests must return explicit model-access restrictions.** Accepted
requests, invalid keys, insufficient credit, rate limits, generic `403` responses,
provider outages or network failures block saving and launch. Fix the reported
issue and retry. The same checks apply to `--yes` and `--offline`; `--dry-run`
makes no requests. See OpenRouter's [error reference](https://openrouter.ai/docs/api_reference/errors-and-debugging).

The probes sample generation models; they cannot certify every model or the
embedding/rerank endpoints. Assigning the full exact profile remains required.
Native-launcher users should run `search-swe configure TASK` to check keys first.
The CLI gate is a local configuration check.

## View or export a profile

```bash
search-swe submission-models
search-swe submission-models --profile reasoning-query-rewriting
search-swe submission-models --profile shared --json
```

These commands work offline without a checkout or credentials. `--json` exports
an `allowed_models` object for guardrail setup; assign it in OpenRouter.
The `:batch` and `:free` suffixes are part of the model IDs.

## Shared: 47 models

### Generation (4)

| OpenRouter model | Exact model ID |
| --- | --- |
| [Qwen3.5-35B-A3B](https://openrouter.ai/qwen/qwen3.5-35b-a3b) | `qwen/qwen3.5-35b-a3b` |
| [Qwen3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b) | `qwen/qwen3.6-35b-a3b` |
| [Qwen3.5-9B](https://openrouter.ai/qwen/qwen3.5-9b) | `qwen/qwen3.5-9b` |
| [Qwen3 30B A3B Instruct 2507](https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507) | `qwen/qwen3-30b-a3b-instruct-2507` |

### Embedding (35)

| OpenRouter model | Exact model ID |
| --- | --- |
| [Qwen3 Embedding 8B](https://openrouter.ai/qwen/qwen3-embedding-8b) | `qwen/qwen3-embedding-8b` |
| [Qwen3 Embedding 4B](https://openrouter.ai/qwen/qwen3-embedding-4b) | `qwen/qwen3-embedding-4b` |
| [Text Embedding 3 Small](https://openrouter.ai/openai/text-embedding-3-small) | `openai/text-embedding-3-small` |
| [Text Embedding 3 Large](https://openrouter.ai/openai/text-embedding-3-large) | `openai/text-embedding-3-large` |
| [Text Embedding 3 Large (batch)](https://openrouter.ai/openai/text-embedding-3-large:batch) | `openai/text-embedding-3-large:batch` |
| [Codestral Embed 2505](https://openrouter.ai/mistralai/codestral-embed-2505) | `mistralai/codestral-embed-2505` |
| [Text Embedding Ada 002](https://openrouter.ai/openai/text-embedding-ada-002) | `openai/text-embedding-ada-002` |
| [Text Embedding Ada 002 (batch)](https://openrouter.ai/openai/text-embedding-ada-002:batch) | `openai/text-embedding-ada-002:batch` |
| [Gemini Embedding 001](https://openrouter.ai/google/gemini-embedding-001) | `google/gemini-embedding-001` |
| [Mistral Embed 2312](https://openrouter.ai/mistralai/mistral-embed-2312) | `mistralai/mistral-embed-2312` |
| [all-MiniLM-L6-v2](https://openrouter.ai/sentence-transformers/all-minilm-l6-v2) | `sentence-transformers/all-minilm-l6-v2` |
| [all-mpnet-base-v2](https://openrouter.ai/sentence-transformers/all-mpnet-base-v2) | `sentence-transformers/all-mpnet-base-v2` |
| [bge-m3](https://openrouter.ai/baai/bge-m3) | `baai/bge-m3` |
| [bge-large-en-v1.5](https://openrouter.ai/baai/bge-large-en-v1.5) | `baai/bge-large-en-v1.5` |
| [multi-qa-mpnet-base-dot-v1](https://openrouter.ai/sentence-transformers/multi-qa-mpnet-base-dot-v1) | `sentence-transformers/multi-qa-mpnet-base-dot-v1` |
| [bge-base-en-v1.5](https://openrouter.ai/baai/bge-base-en-v1.5) | `baai/bge-base-en-v1.5` |
| [all-MiniLM-L12-v2](https://openrouter.ai/sentence-transformers/all-minilm-l12-v2) | `sentence-transformers/all-minilm-l12-v2` |
| [paraphrase-MiniLM-L6-v2](https://openrouter.ai/sentence-transformers/paraphrase-minilm-l6-v2) | `sentence-transformers/paraphrase-minilm-l6-v2` |
| [Multilingual-E5-Large](https://openrouter.ai/intfloat/multilingual-e5-large) | `intfloat/multilingual-e5-large` |
| [E5-Base-v2](https://openrouter.ai/intfloat/e5-base-v2) | `intfloat/e5-base-v2` |
| [E5-Large-v2](https://openrouter.ai/intfloat/e5-large-v2) | `intfloat/e5-large-v2` |
| [GTE-Large](https://openrouter.ai/thenlper/gte-large) | `thenlper/gte-large` |
| [GTE-Base](https://openrouter.ai/thenlper/gte-base) | `thenlper/gte-base` |
| [Llama Nemotron Embed VL 1B V2 (free)](https://openrouter.ai/nvidia/llama-nemotron-embed-vl-1b-v2:free) | `nvidia/llama-nemotron-embed-vl-1b-v2:free` |
| [Embed V1 0.6B](https://openrouter.ai/perplexity/pplx-embed-v1-0.6b) | `perplexity/pplx-embed-v1-0.6b` |
| [Embed V1 4B](https://openrouter.ai/perplexity/pplx-embed-v1-4b) | `perplexity/pplx-embed-v1-4b` |
| [Gemini Embedding 2 Preview](https://openrouter.ai/google/gemini-embedding-2-preview) | `google/gemini-embedding-2-preview` |
| [Gemini Embedding 2](https://openrouter.ai/google/gemini-embedding-2) | `google/gemini-embedding-2` |
| [Nemotron 3 Embed 1B (free)](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free) | `nvidia/nemotron-3-embed-1b:free` |
| [voyage-4-large](https://openrouter.ai/voyageai/voyage-4-large) | `voyageai/voyage-4-large` |
| [voyage-4](https://openrouter.ai/voyageai/voyage-4) | `voyageai/voyage-4` |
| [voyage-4-lite](https://openrouter.ai/voyageai/voyage-4-lite) | `voyageai/voyage-4-lite` |
| [voyage-multimodal-3.5](https://openrouter.ai/voyageai/voyage-multimodal-3.5) | `voyageai/voyage-multimodal-3.5` |
| [voyage-code-4](https://openrouter.ai/voyageai/voyage-code-4) | `voyageai/voyage-code-4` |
| [LFM2.5-Embedding-350M (free)](https://openrouter.ai/liquid/lfm-2.5-embedding-350m:free) | `liquid/lfm-2.5-embedding-350m:free` |

### Rerank (8)

| OpenRouter model | Exact model ID |
| --- | --- |
| [rerank-2.5-lite](https://openrouter.ai/voyageai/rerank-2.5-lite) | `voyageai/rerank-2.5-lite` |
| [rerank-2.5](https://openrouter.ai/voyageai/rerank-2.5) | `voyageai/rerank-2.5` |
| [Llama Nemotron Rerank VL 1B V2 (free)](https://openrouter.ai/nvidia/llama-nemotron-rerank-vl-1b-v2:free) | `nvidia/llama-nemotron-rerank-vl-1b-v2:free` |
| [Rerank v3.5](https://openrouter.ai/cohere/rerank-v3.5) | `cohere/rerank-v3.5` |
| [Rerank 4 Fast](https://openrouter.ai/cohere/rerank-4-fast) | `cohere/rerank-4-fast` |
| [Rerank 4 Pro](https://openrouter.ai/cohere/rerank-4-pro) | `cohere/rerank-4-pro` |
| [rerank-3-lite](https://openrouter.ai/voyageai/rerank-3-lite) | `voyageai/rerank-3-lite` |
| [rerank-3](https://openrouter.ai/voyageai/rerank-3) | `voyageai/rerank-3` |

## Reasoning query rewriting: 17 models

### Generation (3)

- `qwen/qwen3.6-35b-a3b`
- `qwen/qwen3.5-35b-a3b`
- `qwen/qwen3.5-9b`

### Embedding (9)

- `qwen/qwen3-embedding-8b`
- `qwen/qwen3-embedding-4b`
- `voyageai/voyage-4-large`
- `voyageai/voyage-4`
- `voyageai/voyage-4-lite`
- `google/gemini-embedding-001`
- `openai/text-embedding-3-large`
- `openai/text-embedding-3-small`
- `baai/bge-m3`

### Rerank (5)

- `voyageai/rerank-2.5`
- `voyageai/rerank-2.5-lite`
- `cohere/rerank-4-pro`
- `cohere/rerank-4-fast`
- `cohere/rerank-v3.5`

## Sources

IDs were checked on **2026-11-01** against OpenRouter's
[generation catalog](https://openrouter.ai/api/v1/models),
[embedding catalog](https://openrouter.ai/api/v1/embeddings/models) and
[rerank listings](https://openrouter.ai/collections/rerank-models), including the
individual model pages above. Availability remains provider-dependent.
The CLI's fixed profiles live in
[`submission_models.py`](../../src/search_swe/submission_models.py).
