# Code Reranker Fine-Tuning

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `code-reranker-finetuning` |
| Version | 1.0.0 |
| Authors | Jianlyu |
| Primary metric | Accuracy@5 improvement normalized by fixed-candidate headroom |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 10800 s |
| Dataset | code-retrieval |
| Hidden queries | 200 |

Fine-tune the supplied `BAAI/bge-reranker-base` weights while preserving architecture, configuration and tokenizer. The fixed first stage combines local BM25 Top-200 with local `BAAI/bge-base-en-v1.5` embedding Top-200 through equal-weight RRF (`k=60`), retaining the whole deduplicated union of 200–400 candidates. Original and submitted rerankers use exactly the same lists. Reward measures mean Accuracy@5 gain normalized by fixed-candidate headroom over all 200 hidden questions.

[raw-instruction.md](raw-instruction.md) preserves the structured source, and [instruction.md](instruction.md) is the complete agent request. Only the prose instruction reaches the agent; the structured source is outside the agent Docker context and mounts.

### Inputs and environment

The corpus has 8,765 code documents and train has 5,000 records with one positive and no supplied negatives. There is no public validation split; training records may be held out locally. An editable starter samples corpus negatives, uses two-candidate cross-entropy and exports unchanged config/tokenizer bytes with safetensors. Only `/app/output/model` is transferred, and the verifier loads it offline with remote code disabled and safetensors required. Both scoring passes load the tokenizer from the trusted `/task/models/bge-reranker-base`, so additional submitted tokenizer metadata cannot change inference. The four required tokenizer files must still match the backbone byte for byte. Submitted scripts are not executed.

Resources are one GPU, 8 CPUs, 32 GiB RAM and 100 GiB storage; agent time is 21,600 seconds (6 hours) and verifier time is 10,800 seconds. First-stage retrieval is capped at 2,700 seconds and both-reranker evaluation at 7,200 seconds. Failures keep zero reward. Both phases use `no-network` and receive no task API keys. The frozen encoder is mounted at `/task/models/bge-base-en-v1.5` for local candidate mining and verifier inference. Its fixed preprocessing takes the first 512 characters, adds no query prefix, truncates tokens to 512, and uses float32 CLS pooling with batch size 32 and L2 normalization. No trajectory judge is added; checkpoint checks and scoring remain deterministic, so they do not by themselves prove training-data provenance compliance.

For baseline mean Accuracy@5 B, submitted mean S and candidate-hit fraction C across all hidden questions, reward is `clamp((S-B)/(C-B), 0, 1)` when C>B and zero otherwise. Every first-stage miss remains in all denominators. B and C are recalculated, not fixed to author measurements. Neural inference uses full question/document pairs, 512-token joint truncation and batch size 16, resolving equal logits by RRF order.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

Only the reranker weights can change; retrieval candidates, architecture and tokenizer remain fixed. Training supplies positives without negatives, so the agent must learn useful distinctions that generalize to hidden queries.

## Verification Explanation

### Historical author measurement

An earlier author-only local A100 run substituted local BGE embeddings for the API: original reranker Accuracy@5 was 1.5% (3/200), candidate ceiling 23.5% (47/200), headroom 22.0 percentage points, with 76,788 scored pairs and 350–399 candidates per query (mean 383.94). RRF before reranking scored 2.5% (5/200). The ceiling is lower than the historical embedding-only Top-500 ceiling of 28.0%. These historical results do not validate the current local inference implementation or demonstrate trained-checkpoint improvement. Retrieval parameters were not changed using those hidden scores. Historical outputs remain in author development evidence, outside the agent and public data.

### Validation

From the repository root, restore inputs with `python scripts/download_assets.py --task code-reranker-finetuning`. Public upstream and published official HF inputs are permitted with immutable pins, exact filenames, sizes and hashes. Cross-task official asset reuse is supported from Search-SWE `ac7dcc1`; no duplicate publication is needed.

Use `python scripts/check_tasks.py tasks/code-reranker-finetuning`, `python scripts/download_assets.py --task code-reranker-finetuning --verify-only`, and `python -B -m unittest discover -s tasks/code-reranker-finetuning/tests -p 'test_*.py' -q`. Launch through `scripts/run_task.sh --task code-reranker-finetuning`, which preserves real Compose GPU reservations with the documented Harbor override.

#### Historical 6-hour coding-model evaluation (v0.3.1)

The October 17 trial evaluated **v0.3.1 with the current 6-hour budget**, using Codex 0.157.1 + OpenRouter `openai/gpt-6-luna`, effort `max`, on one A100 40GB. It completed normally, without agent timeout, trial errors or retries. Agent execution took **10,901.70 seconds (3 hours 2 minutes)** and separate verification **1,398.98 seconds (23 minutes 19 seconds)**.

On all 200 hidden questions, baseline Accuracy@5 was **0.015 (3/200)**, submitted Accuracy@5 **0.09 (18/200)**, candidate ceiling **0.235 (47/200)**, and final reward **0.3409090909**. The checkpoint loaded offline and passed the fixed-backbone/tokenizer checks. The task has no semantic or trajectory judge. The model reported 56.6% Accuracy@5 on its own 500-query training holdout; that local measure is separate from the hidden result above. No task constraints or scoring were changed in response to the result.

The run used the README's `bash scripts/run_task.sh` entry directly in the right-hand Herdr pane. Results are in `jobs/code-reranker-finetuning-codex-openrouter-luna-max-20261017-6h-attempt3/2026-10-17__01-32-07/`; author records are in `contributing/dev/code-reranker-finetuning/2026-10-17-6h/`. The evaluated instruction SHA-256 is `d62f93219ce821e2ebe23510f5983e984af7ff567cc74cec6649fda7868a9e81`. Both temporary GPU UUID bindings were restored to portable one-GPU reservations after completion, and the GPU 3 reservation was released. At that point all other runtime files matched the prelaunch review snapshot; v0.3.2 subsequently fixes tokenizer loading as described above.

On October 17, against `ac7dcc1`, merge-ready and release checks, all 19 asset hashes, 25 task tests and the 174-test shared suite passed. The 5,000 training queries and 200 hidden query texts have no exact overlap. The earlier offline encoder smoke check also passed. The consolidated author review is `contributing/dev/contribution-readiness/2026-10-17/REVIEW.md`.

#### Earlier 12-hour evaluation

The October 15–16 trial used v0.3.0 with a 12-hour budget. It took 33,677.75 seconds in the agent phase and scored **0.2954545455** (submitted Accuracy@5 **0.08**). Its job is `jobs/evaluations/code-reranker-finetuning/codex/openai/gpt-6-luna/max/attempt-1/2026-10-15__14-05-36/`. A mistakenly started duplicate attempt 2 was cancelled. These records remain historical; the completed 6-hour trial above supplies the evidence for the current training budget.

#### PR #17 tokenizer isolation fix (v0.3.2)

Both model loads now obtain their tokenizer exclusively from the trusted
backbone. The submitted directory is still used for model weights, and the four
required tokenizer files retain their byte-for-byte checks. Additional files
such as `added_tokens.json` are never loaded as tokenizer configuration.

The new offline regression uses a real small XLM-R tokenizer and model: adding
one metadata file changes token IDs and logits under the old loader, with the
existing tokenizer files, vocabulary size, configuration and weights unchanged.
The fixed loader produces identical token IDs and scores for both checkpoints.
A second case checks that malformed submitted metadata is never loaded. Both
regressions fail against the reviewed `b78f354` loader and pass after this fix.

On October 17, the revised package passed all **27 task-local tests**, merge-ready
checks against `ac7dcc145925d98afd2b0db1112d7c0ad8ba1460`, all **19 asset** hash
checks, release checks, and the **174-test shared suite**. Instructions, training
budget, candidate generation and reward mapping are unchanged.

The saved six-hour Luna checkpoint was then replayed through native Harbor
Oracle installation, normal checkpoint transfer, and the **v0.3.2 separate
verifier**, with the original offline policy and one A100 40GB. This is a fresh
full verifier execution, not a new training trial. Verification took **1,398.93
seconds**, completed without errors, and exactly reproduced **B=0.015,
S=0.09, C=0.235, reward=0.3409090909**, over 76,788 candidate pairs.

Evidence: `jobs/code-reranker-finetuning-regrade-20261017-pr17/2026-10-17__13-47-11/task__jQETt8r/`;
author records and the exact replay configuration are under
`contributing/dev/code-reranker-finetuning/2026-10-17-pr17/`. The temporary GPU
binding exists only in that author-only task copy; the contributed Compose
files retain portable one-GPU reservations. No new six-hour coding-model trial
was run: the existing trained checkpoint and unchanged agent instructions are
reused, while the corrected tokenizer path is covered by the new regressions
and this complete regrade.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

### Sources and structural references

Corpus and train reuse the exact hashes and named paths from the current formal `tasks/code-embedding-finetuning/assets.json`, pinned to official dataset revision `6713b1eb7474e0768e906a0151c76af92f0cfcdd`. The reranker retains its original `BAAI/bge-reranker-base` model revision `2cfc18c9415c912f9d8155881c133215df768a70`. The local embedding model is pinned to `BAAI/bge-base-en-v1.5` revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`; all eleven model/tokenizer/metadata files were downloaded and SHA-256 verified. No data/model bytes were republished. See [SOURCES.md](SOURCES.md) for provenance and usage terms. Published inputs may be reused at their original paths. The reused hidden split is runtime-isolated but visible in the repository and has a known contamination risk.

Read-only references: `tasks/code-embedding-finetuning` for GPU training, corpus provenance, fixed-backbone model delivery and offline loading; `tasks/long-document-reranking` for candidate reranking and deterministic quality scoring. This task optimizes reranker weights with local embedding plus BM25 candidates, has no public validation split, and keeps its headroom-normalized reward instead of the reference metrics.
