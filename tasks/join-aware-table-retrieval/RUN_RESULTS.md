# Run evidence reconciled on 2026-10-23

The saved trial passed 1/10 complete table-and-join sets. All ten outputs were valid and within the query deadline. Scoring is deterministic; no model judge is configured.

| Field | Observed value |
| --- | --- |
| Current package | `0.6.0` |
| Saved agent trial version | `0.6.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.1 |
| Raw metric | complete table-and-join coverage = 0.1 |
| Archived final reward | 0.1 |
| Required trajectory judge | Not configured; deterministic scoring |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `ae454d3e90d118b3eaaf6c3e5965ba1e64d1610e233712c5778666a94b217680` |
| Saved evaluation SHA-256 | `99efddb016378d5a8a912e8e589fda71f55257d58ef8e59e7ef200136a91029b` |
| Saved reward SHA-256 | `8f86c9e820010f98cf2d999e1c14d81982832bb2633e2b8414f88e7754b21fc7` |

The records are retained in the author's surrounding workspace under
`task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/harbor/2026-10-14__23-20-38/join-aware-table-retrieval__PkCnwyj/verifier/report.json` and
`task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/harbor/2026-10-14__23-20-38/join-aware-table-retrieval__PkCnwyj/verifier/reward.txt`. These are author-local evidence
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
