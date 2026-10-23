# Run evidence reconciled on 2026-10-23

The saved v0.2.1 trial returned 0/20 complete sets. Version 0.2.2 now supplies eight public examples (original three plus five independently verified additions); its twenty hidden cases are unchanged. No fresh v0.2.2 agent trial was run. The historical zero must not be presented as a new-version measurement.

| Field | Observed value |
| --- | --- |
| Current package | `0.2.2` |
| Saved agent trial version | `0.2.1` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Historical trial with the previous public split |
| Current available score | 0 |
| Raw metric | ExactSetAccuracy = 0 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `d5b276d357b2df5c1c664beeaee9fdf99b4116670b260d4437e744c40d548957` |
| Saved evaluation SHA-256 | `f8ec981ea620be1de331c6758a22217f33167a4fbadd3d0ce106a4a417dca197` |
| Saved reward SHA-256 | `a82a52709516ffd69da56259559c6fd0a2016b05608572e22e9a36842119d209` |

The records are retained in the author's surrounding workspace under
`task_results/biomedical-graph-retrieval/codex-openrouter-gpt-6-luna-max-v021-20261014T164416Z/jobs/2026-10-15__00-44-54/biomedical-graph-retrieval__7iyRMF9/verifier/biomedical-graph-retrieval-eval/evaluation.json` and
`task_results/biomedical-graph-retrieval/codex-openrouter-gpt-6-luna-max-v021-20261014T164416Z/jobs/2026-10-15__00-44-54/biomedical-graph-retrieval__7iyRMF9/verifier/reward.json`. These are author-local evidence
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
