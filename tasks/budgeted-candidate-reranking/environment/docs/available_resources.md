# Fixed local resources

Only Qwen/Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` is allowed for model inference. It is provided read-only under `/task/models/Qwen3-1.7B` with its original tokenizer, configuration and Apache-2.0 model license. The trusted runtime verifies every installed file against `model-hashes.json`. Do not modify, fine-tune, quantize, substitute or load another checkpoint. The supported backend is Transformers 5.15.1 with PyTorch 2.9.0+cu130, BF16, greedy decoding, `enable_thinking=False` and the original chat template. Deployment JSON may choose `sdpa`/`eager` and 1–16 CPU threads only. No submitted executable callbacks, custom templates, adapters or package installation are loaded by the model process. Every model forward must pass through the trusted pipe interface during development and final verification.

The 43 judged DL2019 public queries have exactly 100 frozen BM25 candidates each and complete official 0–3 qrels. All 54 judged DL2020 queries are used privately by the verifier. Original TREC benchmarks are publicly obtainable, but outside evaluation judgments and answer maps must not be used. No full-corpus index or new retrieval stage is supplied. Candidate text and initial scores may be used locally without model calls. Use only supplied data/models, with no external services, models, labels, query-to-answer tables or precomputed test rankings.

The MS MARCO passage text remains subject to its original noncommercial research terms: https://microsoft.github.io/msmarco/. This task does not relicense it under the repository's code license. The candidate-generation source/version and immutable model pin are documented in the author README.

No OpenRouter/task-model API, additional retrieval/reranking API or answer/trajectory judge is available to submitted code. Both phases use no-network. Bypassing the model entry point, tampering with accounting or accessing grader outputs/hidden labels invalidates the submission. The trusted final verifier reconstructs the configured backend independently.


## Optional starting implementations

`/task/baselines/bm250` returns the original BM25 Top-10. `list15` and `point10`
demonstrate listwise and pointwise reranking using the same fixed local model
and token budget. Each directory contains a runnable strategy. Copy an example
into your submission or implement a different strategy; no starter is installed
in `/app`. See the task instruction for the complete JSONL request protocol.
