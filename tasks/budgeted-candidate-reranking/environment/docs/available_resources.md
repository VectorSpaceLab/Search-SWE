# Available Resources

Use the supplied candidates and fixed local model through the trusted pipe interface.

## Local resources

- `/task/data/public.jsonl.gz`: 43 public DL2019 queries with exactly 100 frozen BM25 candidates each.
- `/task/data/public-qrels.json`: complete public relevance labels on the 0–3 scale.
- `/task/models/Qwen3-1.7B`: fixed model, tokenizer, configuration and license.
- `/task/runtime/evaluate.py`: public interface and resource check.
- `/task/baselines/`: optional starting implementations.

No full-corpus index or new retrieval stage is supplied. Candidate text and initial scores may be used locally without model calls. Preserve the supplied candidate pool.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Fixed local model

Only Qwen/Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` is allowed for model inference. It is provided read-only under `/task/models/Qwen3-1.7B` with its original tokenizer, configuration and Apache-2.0 model license. Do not modify, fine-tune, quantize, substitute or load another checkpoint. The supported backend is Transformers 5.15.1 with PyTorch 2.9.0+cu130, BF16, greedy decoding, `enable_thinking=False` and the original chat template. Deployment JSON may choose `sdpa`/`eager` and 1–16 CPU threads only. No submitted executable callbacks, custom templates, adapters or package installation are loaded by the model process. Every model forward must pass through the trusted pipe interface during development and final verification.

## Optional starting implementations

`/task/baselines/bm250` returns the original BM25 Top-10. `list15` and `point10` demonstrate listwise and pointwise reranking using the same fixed local model and token budget. Each directory contains a runnable strategy. Copy an example into your submission or implement a different strategy; no starter is installed in `/app`. See the task instruction for the complete JSONL request protocol.

## Source terms

The MS MARCO passage text remains subject to its original noncommercial research terms. This task does not relicense it under the repository's code license.

## Network and resource restrictions

No task API key, external API, external service or download is available. Development and final verification run without network access. Use only the supplied data and model through the fixed model entry point. Do not use external services, models, labels, query-to-answer tables or precomputed test rankings. Bypassing that entry point, tampering with accounting or accessing grader outputs/hidden labels invalidates the submission.
