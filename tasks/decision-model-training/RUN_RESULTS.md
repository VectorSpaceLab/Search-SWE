# Run evidence reconciled on 2026-10-23

The saved verifier reported 2,360/4,200 correct predictions. This task has deterministic offline scoring and no model judge.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.0` |
| Saved agent trial version | `0.1.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.561904761904762 |
| Raw metric | accuracy = 0.561904761904762 |
| Archived final reward | 0.561904761904762 |
| Required trajectory judge | Not configured; deterministic scoring |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `769c11900ec4d4ca69449fde55e2e075e2304092fd4968ef5d998f1ad1c940cb` |
| Saved evaluation SHA-256 | `33d23384f338f33870c69cea55ee4fc70e911d2bdc20c52f2bd9bb7e9b10f16a` |
| Saved reward SHA-256 | `abbe304e217be1f44102c6bcbf987afd299293d59a30a705ec79251d2881c410` |

The records are retained in the author's surrounding workspace under
`task_results/decision-model-training/codex-openrouter-gpt-6-luna-max-v010-20261022T135859Z/jobs/2026-10-22__21-59-35/decision-model-training__rnbK9nx/verifier/evaluation.json` and
`task_results/decision-model-training/codex-openrouter-gpt-6-luna-max-v010-20261022T135859Z/jobs/2026-10-22__21-59-35/decision-model-training__rnbK9nx/verifier/reward.json`. These are author-local evidence
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
