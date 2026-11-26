# Quantity-aware Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `quantity-aware-retrieval` |
| Version | 1.0.0 |
| Authors | Bingyu |
| Primary metric | Normalized binary nDCG@10 |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 4800 s |
| Dataset | MedQuant, original passages and qrels |
| Public queries | 0 |
| Hidden queries | 209 |

## Overview

Author: **Bingyu**. This Search-SWE task uses MedQuant. The required deliverable is an executable retrieval system. Resources include labeled examples, Qwen3-Embedding-0.6B and documented OpenRouter/Jina APIs. No baseline implementation, authoring helper, or precomputed document vectors are provided to the agent.

### Data and split

| Input | Size |
| --- | ---: |
| Corpus | 153,252 original passages |
| Labeled examples (`data/examples.jsonl`) | 80,000; 12,453 distinct query texts |
| Public retrieval validation | None |
| Private evaluation | 209 queries retained from the original 210 |

One query with invalid positive labels has been removed; see [the validation record](VALIDATION.md). Corpus text and the retained queries and positive sets are unchanged, except opaque ID renaming. Corpus order is preserved. The source corpus's quantity fields and query condition/unit/value annotations are not exposed. The examples include synthetic edited passages and do not form a corpus-ID relevance file. The agent-facing instructions describe inputs, outputs, constraints and scoring without prescribing an implementation method.

All retained evaluation questions remain private. Benchmark concepts and their source expansion components were excluded during training generation. A later review also checked physical/clinical examinations, death-rate, rebleeding, placebo, uric-acid and pain/VAS families. This automatic exclusion and limited family review do not prove universal semantic isolation. The retained query texts and positive sets have not been rewritten.

Authoring sources, the split manifest, calibration evidence and validation fixtures are in `../../../task_development/quantity-aware-retrieval/`, outside this task. No `authoring/`, `bundled/`, `environment/tools/` or public starter is part of the package.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-11-04 | 1.0.0 | Added initial task |

## Difficulty Explanation

Clinical relevance depends on numerical conditions as well as topic similarity. The system must interpret quantities and units from the supplied text and generalize from synthetic examples to the original hidden questions.

## Verification Explanation

### Evaluation

The engine implements `/app/build.sh` and `/app/run.sh`, as specified in `instruction.md`. A separate verifier runs the submission as UID 10001, with `/app` read-only and hidden data/reward paths protected. It reveals one question per call with a fresh request ID. Build/service startup has 1,200 seconds; queries have a hard **5 seconds**, including API/network waiting. A timeout scores that query zero. Other executable/output failures invalidate the run.

Quality is mean binary nDCG@10, using the complete original positive set for IDCG, capped at ten positions. The frozen reference is BM25 and Qwen3-Embedding-8B, top-1000 each, fused with RRF constant 60.

| Reference scope | Mean nDCG@10 |
| --- | ---: |
| Retained 209 questions | 0.18472070182938527 |
| Four-decimal reward anchor | **0.1847** |

For raw private score Q and B = 0.1847, reward is `max(0, min(1, (Q-B)/(1-B)))`. The anchor uses the four-decimal rounding explicitly chosen by the user. The reference is recalculated over the retained queries from the archived single-A100 hybrid retrieval results in `../../../task_development/quantity-aware-retrieval/research/medquant-baselines-v1/per-query-results.jsonl` (`methods.hybrid`); [VALIDATION.md](VALIDATION.md) records the exclusion and calculation. No per-query baseline oracle or choice of the best model on private results is used.

An independent trajectory integrity judge uses the repository's pinned RewardKit 0.2.0/DeepSeek configuration. Its credentials are not passed to submission processes. A failed or rejecting mandatory judge cannot yield a positive final reward. Deterministic grader checks and synthetic perfect-answer fixtures do not substitute for a live coding-agent/judge trial.

The environment is one A100 40GB, 16 CPU cores, 32 GiB RAM, 100 GiB storage, and a 21,600-second (6-hour) agent phase shared by implementation, optional training and validation. Both phases use the repository shared CUDA 13.0/Python 3.12 image. The GPU environment document is copied from `docker/gpu/environment.md`.

### Verifier query order

The verifier shuffles the private query list with a fixed local seed for reproducible request ordering. Each invocation still assigns fresh opaque request IDs; IDs must be echoed without assuming a relationship to document labels. Building and retrieval are not repeated. This removes unnecessary order variation while preserving the original per-query deadline and normalized nDCG metric.

## Running the Task

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [recorded run evidence](VALIDATION.md#run-evidence-reconciled-on-2026-10-23) for historical run outcomes and publication status. Existing source terms and attribution remain applicable.

```bash
python scripts/assets/download_assets.py --task quantity-aware-retrieval --verify-only
python -m unittest discover -s tasks/quantity-aware-retrieval/authoring/tests -p 'test_*.py'
python scripts/evaluation/run_task.py --task quantity-aware-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --dry-run
```

The coding model and verifier credentials are configured in the repository's ignored `.env`; do not place credentials in this task. Task APIs are optional. The verifier judge requires `VERIFIER_OPENAI_BASE_URL` and `VERIFIER_OPENAI_API_KEY`. A real coding-model trial and live judge health check are separate from package/unit/container smoke tests. See `VALIDATION.md` for commands actually run, observed results, and unperformed release/evaluation steps.

See [VALIDATION.md](VALIDATION.md) for recorded run outcomes, judge health and validation evidence.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## References

- **Task source** — [DeepQuant (Findings of ACL 2025)](https://aclanthology.org/2025.findings-acl.1220/)
- **Data source** — MedQuant passages and judgments from [QuantityAwareRankers](https://github.com/satya77/QuantityAwareRankers). [Numbers Matter! (Findings of EMNLP 2024)](https://aclanthology.org/2024.findings-emnlp.707/)
- **Model source** — [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).
- **Provenance details** — [Training data construction, source revisions, and limitations](SOURCES.md)
