# Run evidence reconciled on 2026-10-23

The saved v0.1.0 evaluation and passing audit are reused. Version 0.1.1 changes only the zero-score baseline to 0.310109, retaining ceiling 0.9901639344262295. The current reward is an offline recalculation from saved Recall@3; no new agent, retrieval or online judge run occurred.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.1` |
| Saved agent trial version | `0.1.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Offline recalculation of saved valid evaluation under the revised baseline |
| Current available score | 0.0156693625514165 |
| Raw metric | Recall@3 = 0.320765027322404 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `954fc3c181416fc4d3b90d13f921961128c88013f83e4478ed0b8d73ee0b8e90` |
| Saved evaluation SHA-256 | `21a485be0fe44578703b41e6ff277113379c95573b434a0504cf4d937b4ef3c6` |
| Saved reward SHA-256 | `0940f1ee26fc6e7c4692160ffad612da09143841dea7e90ddbf3c3ab6386c112` |

The records are retained in the author's surrounding workspace under
`task_results/methodology-inspiration-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T093112Z/jobs/2026-10-22__17-31-54/methodology-inspiration-retrieva__PbJPQsK/verifier/methodology-inspiration-retrieval-eval/evaluation.json` and
`task_results/methodology-inspiration-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T093112Z/jobs/2026-10-22__17-31-54/methodology-inspiration-retrieva__PbJPQsK/verifier/reward.json`. These are author-local evidence
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
