# Run evidence reconciled on 2026-10-23

The v0.4.3 trial scored 1/12 with valid evidence evaluation and a successful passing trajectory audit. The task uses DeepSeek V4.1 Flash evidence judging and a 30-second per-query deadline. The agent reached its development deadline before verifier scoring completed.

| Field | Observed value |
| --- | --- |
| Current package | `0.4.3` |
| Saved agent trial version | `0.4.3` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.0833333333 |
| Raw metric | sentence evidence accuracy = 0.0833333333333333 |
| Archived final reward | 0.0833333333 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 65536 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `7fb149bf72243db76a8f6c467928978a3c28366fb974efe0058e573591f6e668` |
| Saved evaluation SHA-256 | `8830a5d65a0e70ef3011a3e6c06eb67e262361f0f2493d3f0505e3d8f95dd5ad` |
| Saved reward SHA-256 | `6576ae69a703e3219da2a8380a23846a562d086db80abc46bd9d27c966bf1a79` |

The records are retained in the author's surrounding workspace under
`task_results/long-pdf-evidence/codex-openrouter-gpt-6-luna-max-v043-20261022T135859Z/jobs/2026-10-22__21-59-35/long-pdf-evidence__VzXzNBH/verifier/long-pdf-evidence-eval/evaluation.json` and
`task_results/long-pdf-evidence/codex-openrouter-gpt-6-luna-max-v043-20261022T135859Z/jobs/2026-10-22__21-59-35/long-pdf-evidence__VzXzNBH/verifier/reward.json`. These are author-local evidence
locations, not public download links. Original trajectories, submitted code,
private evaluation outputs and credentials are not published in this task.
The current instruction matches the evaluated instruction; where public data,
normalization or verifier behavior changed, the limitations above apply.

Public inputs have immutable source revisions, sizes and SHA-256 values in
`assets.json`. Unchanged published data/model references are retained.
The only new data in this release are the biomedical and filtered-ANN public
validation pairs, published through [HF PR #8](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/8) at
`234406eb7e304478e48905829fc0d3233f5a9f1f`. All 52,417 earlier dataset manifest records were preserved.
Publication does not resolve outstanding upstream licensing or independent
quality-review limitations recorded in the task's provenance.

This release reconciliation uses existing model results. It does not start a
fresh coding agent, GPU training job or paid judge call. Task-local regression
checks are recorded in the contribution PR; earlier construction and runtime
records remain in `VALIDATION.md` where present.
