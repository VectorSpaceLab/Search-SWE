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

Author: **Bingyu**. This Search-SWE task uses
MedQuant. The required deliverable is an executable retrieval system. Resources
include labeled examples, Qwen3-Embedding-0.6B and documented OpenRouter/Jina APIs. No
baseline implementation, authoring helper, or precomputed document vectors are
provided to the agent.

### Data and split

| Input | Size |
| --- | ---: |
| Corpus | 153,252 original passages |
| Labeled examples (`data/examples.jsonl`) | 80,000; 12,453 distinct query texts |
| Public retrieval validation | None |
| Private evaluation | 209 queries retained from the original 210 |

One query with invalid positive labels has been removed; see
[the validation record](VALIDATION.md). Corpus text and the retained queries and
positive sets are unchanged, except opaque ID renaming. Corpus order is preserved. The source corpus's
quantity fields and query condition/unit/value annotations are not exposed.
The examples include synthetic edited passages and do not form a corpus-ID
relevance file. The agent-facing instructions describe inputs, outputs,
constraints and scoring without prescribing an implementation method.

All retained evaluation questions remain private. Benchmark concepts and their
source expansion components were excluded during training generation. A later
review also checked physical/clinical examinations, death-rate, rebleeding,
placebo, uric-acid and pain/VAS families. This automatic exclusion and limited
family review do not prove universal semantic isolation. The retained query texts
and positive sets have not been rewritten.

Authoring sources, the split manifest, calibration evidence and validation
fixtures are in `../../../task_development/quantity-aware-retrieval/`, outside
this task. No `authoring/`, `bundled/`, `environment/tools/` or public starter is
part of the package.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Removed one query with invalid positives and recalculated the 209-query baseline |

## Difficulty Explanation

Clinical relevance depends on numerical conditions as well as topic similarity. The system must interpret quantities and units from the supplied text and generalize from synthetic examples to the original hidden questions.

## Verification Explanation

### Evaluation

The engine implements `/app/build.sh` and `/app/run.sh`, as specified in
`instruction.md`. A separate verifier runs the submission as UID 10001, with
`/app` read-only and hidden data/reward paths protected. It reveals one question
per call with a fresh request ID. Build/service startup has 1,200 seconds;
queries have a hard **5 seconds**, including API/network waiting. A timeout
scores that query zero. Other executable/output failures invalidate the run.

Quality is mean binary nDCG@10, using the complete original positive set for
IDCG, capped at ten positions. The frozen reference is BM25 and
Qwen3-Embedding-8B, top-1000 each, fused with RRF constant 60.

| Reference scope | Mean nDCG@10 |
| --- | ---: |
| Retained 209 questions | 0.18472070182938527 |
| Four-decimal reward anchor | **0.1847** |

For raw private score Q and B = 0.1847, reward is
`max(0, min(1, (Q-B)/(1-B)))`. The anchor uses the four-decimal rounding explicitly
chosen by the user. The reference is recalculated over the retained queries from
the archived single-A100 hybrid retrieval results in
`../../../task_development/quantity-aware-retrieval/research/medquant-baselines-v1/per-query-results.jsonl`
(`methods.hybrid`); [VALIDATION.md](VALIDATION.md) records the exclusion and calculation. No per-query baseline
oracle or choice of the best model on private results is used.

An independent trajectory integrity judge uses the repository's pinned
RewardKit 0.2.0/DeepSeek configuration. Its credentials are not passed to
submission processes. A failed or rejecting mandatory judge cannot yield a
positive final reward. Deterministic grader checks and synthetic perfect-answer
fixtures do not substitute for a live coding-agent/judge trial.

The environment is one A100 40GB, 16 CPU cores, 32 GiB RAM, 100 GiB storage, and
a 21,600-second (6-hour) agent phase shared by implementation, optional training and
validation. Both phases use the repository shared CUDA 13.0/Python 3.12 image.
The GPU environment document is copied from `docker/gpu/environment.md`.

### Local operation and validation

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

```bash
python scripts/download_assets.py --task quantity-aware-retrieval --verify-only
python -m unittest discover -s tasks/quantity-aware-retrieval/tests -p 'test_*.py'
python scripts/run_task.py --task quantity-aware-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --dry-run
```

The coding model and verifier credentials are configured in the repository's
ignored `.env`; do not place credentials in this task. Task APIs are optional.
The verifier judge requires `VERIFIER_OPENAI_BASE_URL` and
`VERIFIER_OPENAI_API_KEY`. A real coding-model trial and live judge health check
are separate from package/unit/container smoke tests. See `VALIDATION.md` for
commands actually run, observed results, and unperformed release/evaluation steps.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

### Provenance and limitations

MedQuant and the underlying training material are from
[QuantityAwareRankers](https://github.com/satya77/QuantityAwareRankers), associated
with [Numbers Matter!](https://aclanthology.org/2024.findings-emnlp.707/).
[DeepQuant](https://aclanthology.org/2025.findings-acl.1220/) is the motivating
quantity-aware retrieval paper; this package does not claim to reproduce its
unreleased exact 150k MedQuant training split.

The benchmark ZIP SHA-256 is
`223fc8c7fcc6fded6a58a16c9d2bf3784c010568310b56355a0682956908e0c8`.
The generated training parent SHA-256 is
`80667d66bf0de233a6d4f0b112daa77c0b4b8f185d78c934642078a95cfef576`.
Generation reused the author functions at commit
`5d2c2e59c938fc816d1614d7cdc56763e54748ed`, with deterministic group seeds,
concept exclusion, deduplication and exact-pair conflict removal. No generation
API calls were made. Labels remain synthetic and noisy; training efficacy has
not been established by a 50k/80k ablation. Original positive-only evaluation
qrels can omit relevant passages. Units follow the source convention; physical
unit conversion or new multi-constraint semantics would require new labels.

[Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/tree/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3)
is pinned to `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`. All ten installed model
files were independently checked against their manifest sizes and SHA-256.
The model card declares Apache-2.0. The enclosing repository's code license does
not establish redistribution rights for the MedQuant/training sources; those
terms remain unresolved and are recorded in the published source notices.
