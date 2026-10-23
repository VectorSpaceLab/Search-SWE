# Run evidence reconciled on 2026-10-23

The v0.4.0 verifier and live integrity audit completed. Macro nDCG@10 was 0.4303102260205993, below the 0.45 gate; median query-batch time was 0.41057249531149864 seconds. The zero is therefore a quality-gate result. A positive-reward final-configuration witness and live adversarial audit calibration remain unestablished.

| Field | Observed value |
| --- | --- |
| Current package | `0.4.0` |
| Saved agent trial version | `0.4.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0 |
| Raw metric | macro nDCG@10 = 0.430310226020599 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `dea7762c163c98d43a21e3eabfa516d2627d704677c54883421bfdb38f13fc8e` |
| Saved evaluation SHA-256 | `c8b5676b33232e8f892f892c93c2ea2137500055032fa5c7e6e5faad96601fcb` |
| Saved reward SHA-256 | `b968c26c370deb6b29fd210d9bb4206f1d14d34014734d2e39c29cc440dd5501` |

The records are retained in the author's surrounding workspace under
`task_results/lightweight-query-retrieval/codex-openrouter-gpt-6-luna-max-v040-20261022T135859Z/jobs/2026-10-22__21-59-35/lightweight-query-retrieval__NXt6iHq/verifier/report.json` and
`task_results/lightweight-query-retrieval/codex-openrouter-gpt-6-luna-max-v040-20261022T135859Z/jobs/2026-10-22__21-59-35/lightweight-query-retrieval__NXt6iHq/verifier/reward.json`. These are author-local evidence
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
