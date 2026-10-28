# Run evidence reconciled on 2026-10-23

The results below describe the historical 778-query evaluation. The 2026-10-28
revision retains 775 queries; see [VALIDATION.md](VALIDATION.md). These historical
model scores have not been recalculated for that revision.

The verifier produced valid nDCG@10 over 778 queries. A command-timeout exception is retained in the original run. This low score does not establish that training a temporal representation is infeasible; that training route remains unvalidated.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.0` |
| Saved agent trial version | `0.1.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.00568542466983154 |
| Raw metric | nDCG@10 = 0.00568542466983154 |
| Archived final reward | 0.00568542466983154 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `7b6333047d5598805c7ff3c09dafc57eabc94f94948362f48b6aca2127f816dc` |
| Saved evaluation SHA-256 | `bf43605f83993f17ab322677b89ccc72d8480a2edfec774e309c26bc65d3dd73` |
| Saved reward SHA-256 | `67e2728d5e01b8ccb84680fb212ae7665a3a9c0d76ef3857334ecef265960da5` |

The records are retained in the author's surrounding workspace under
`task_results/chunqiu-temporal-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T070131Z/jobs/2026-10-22__15-12-53/chunqiu-temporal-retrieval__THPbLEr/verifier/chunqiu-temporal-retrieval-eval/evaluation.json` and
`task_results/chunqiu-temporal-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T070131Z/jobs/2026-10-22__15-12-53/chunqiu-temporal-retrieval__THPbLEr/verifier/reward.json`. These are author-local evidence
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
