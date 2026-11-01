# OpenRouter submission-key model allowlists

[Documentation index](../README.md)

**Model allowlists are mandatory for every enabled submission API key. Use its exact profile:**

| Host variable | Profile | Generation | Embedding | Rerank | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| `OPENROUTER_API_KEY` | Shared | 4 | 35 | 8 | **47** |
| `REASONING_QUERY_REWRITING_OPENROUTER_API_KEY` | Reasoning query rewriting | 3 | 9 | 5 | **17** |

These profiles keep a small set of lightweight generation models and a broad
selection of embedding and rerank models. **`qwen/qwen3-reranker-8b` is deliberately
excluded from both profiles to control API cost.** The lists are fixed benchmark
configuration; new OpenRouter releases are added only through an explicit profile
update. The reasoning-query-rewriting list is a strict subset of the shared list.

The profiles describe the APIs available to **submitted search programs**.
Coding-agent keys (`AGENT_OPENROUTER_API_KEY`) and verifier/answer-judge keys use
separate model access. Each task's `environment/docs/available_resources.md`
defines the permitted models, endpoints and operations within the key's available
resources. A key's allowlist is an upper bound; task-specific restrictions still
apply. Jina services use their independently configured `JINA_API_KEY`.

## Configure the keys

1. Create a submission key for the shared profile and, when running
   reasoning-query-rewriting with OpenRouter resources, a separate key for its
   dedicated profile.
2. In the OpenRouter workspace's **Guardrails** page, create a guardrail with
   exactly the corresponding **Allowed Models** below. Save it and assign it
   under **API Keys** to the matching submission key. An empty model allowlist
   allows all models. Check the effective restrictions after assignment.
3. Enter the key through `search-swe configure TASK`, or put it in the matching
   variable in the ignored `.env`. Existing values are reused; new tasks request
   only missing variables. Use `--edit-credentials` to replace an existing key.

See [OpenRouter's guardrail setup and assignment documentation](https://openrouter.ai/docs/guides/features/guardrails).
Guardrails assigned directly to submission keys preserve separate coding-agent
and judge access; their keys must allow the models their roles use.

## Required CLI checks

After configuration is confirmed, and before each evaluation batch starts,
`search-swe configure` and `search-swe run` check the submission keys used by the
selected tasks. Existing keys are checked again; optional services left unset
and keys belonging only to other tasks need no check.

For each enabled key, the CLI sends three short Chat Completions requests with
`max_tokens=1` to distinct out-of-list models. It chooses candidates using system
randomness from a fresh public OpenRouter catalog, across different model
vendors, with at least 25 eligible candidates. For reasoning-query-rewriting,
one request checks the shared-only Qwen generation model to catch accidental
assignment of the wider profile; the other two are random. Accepted requests
may incur small API charges. Correct model-allowlist denials stop at OpenRouter.

All three requests must return explicit model-access restrictions. An accepted
request, or an inconclusive result such as invalid credentials, insufficient
credits, rate limiting, generic `403`, provider downtime or a network failure,
stops configuration and evaluation with a corrective error. The CLI completes
these checks before saving new settings, downloading assets or launching tasks.
Fix the reported issue and repeat the command. This applies to `--yes` and
`--offline` too: the latter caches asset/model selection, while these checks
need connectivity. `--dry-run` previews the required checks without making
requests or starting evaluations.

These sampled generation requests catch configuration mistakes; they do not
audit every model or the embedding/rerank endpoints. Assigning the exact full
profile remains required, including the `qwen/qwen3-reranker-8b` exclusion. The
CLI gate is a local setup check, not a tamper-proof verifier. Native launcher
users also need the same profiles; run `search-swe configure TASK` to check their
keys before using the lower-level launcher.

OpenRouter documents the distinction between model restrictions and other
failures in its [guardrail guide](https://openrouter.ai/docs/guides/features/guardrails)
and [error reference](https://openrouter.ai/docs/api_reference/errors-and-debugging).

## View or export a profile

The wizard shows the applicable profile and its model count once per key,
including for existing keys, without adding another confirmation prompt. List
all IDs or export the `allowed_models` JSON object on demand:

```bash
search-swe submission-models
search-swe submission-models --profile reasoning-query-rewriting
search-swe submission-models --profile shared --json
search-swe submission-models --profile reasoning-query-rewriting --json
```

These commands work offline, without a checkout or credentials. Exporting a
profile produces data for guardrail setup; assignment takes place in OpenRouter.
The `:batch` and `:free` suffixes below are part of the model IDs.

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

## Sources and maintenance

IDs were checked on **2026-11-01** against the [generation catalog](https://openrouter.ai/api/v1/models),
[embedding catalog](https://openrouter.ai/api/v1/embeddings/models),
[rerank model pages](https://openrouter.ai/collections/rerank-models), and the
individual pages linked above. The batch variants have their own model pages:
[Text Embedding 3 Large (batch)](https://openrouter.ai/openai/text-embedding-3-large:batch)
and [Text Embedding Ada 002 (batch)](https://openrouter.ai/openai/text-embedding-ada-002:batch).
Availability remains provider-dependent; the fixed allowlist is not a connectivity
or availability test.

The CLI profiles are maintained in
[`src/search_swe/submission_models.py`](../../src/search_swe/submission_models.py).
Update this guide alongside intentional profile changes. CLI regression tests
check profile counts, subset membership, exclusions, suffixes, and consistency
between the documented IDs and exported data.
