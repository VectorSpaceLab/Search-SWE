# Run evidence reconciled on 2026-10-23

The results below describe the historical 210-query evaluation. The 2026-10-28
revision retains 209 queries and uses baseline 0.1847; see [VALIDATION.md](VALIDATION.md).
These historical model scores have not been recalculated for that revision.

The saved v0.1.0 evaluation and passing audit are reused. Version 0.1.1 changes the zero-score baseline to 0.1838, with ceiling 1. The current reward is an offline recalculation from saved nDCG@10; no new agent, retrieval or online judge run occurred.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.1` |
| Saved agent trial version | `0.1.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Offline recalculation of saved valid evaluation under the revised baseline |
| Current available score | 0.161629686378338 |
| Raw metric | nDCG@10 = 0.315722150021999 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `665034497f64940954bb826e66b437b3f2b14ceff924453d860d5c5f1b911bfd` |
| Saved evaluation SHA-256 | `2c03b5d687ba6f1861a3ed89bf0980777167f09d674c5901e733a60d96e6fa58` |
| Saved reward SHA-256 | `ad5763267f2130860122cb050c4a3ae726789f47fac090c3fc2d55d06b02ca30` |

The records are retained in the author's surrounding workspace under
`task_results/quantity-aware-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T135859Z/jobs/2026-10-22__21-59-35/quantity-aware-retrieval__63D7YGN/verifier/quantity-aware-retrieval-eval/evaluation.json` and
`task_results/quantity-aware-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T135859Z/jobs/2026-10-22__21-59-35/quantity-aware-retrieval__63D7YGN/verifier/reward.json`. These are author-local evidence
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
