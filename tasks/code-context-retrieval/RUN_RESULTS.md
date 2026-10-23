# Run evidence reconciled on 2026-10-23

The agent reached its development deadline; subsequent verifier scoring completed. Mean line-level F1 is a valid retrieval result, not a clean agent-completion claim.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.0` |
| Saved agent trial version | `0.1.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.171468759323379 |
| Raw metric | mean line F1 = 0.171468759323379 |
| Archived final reward | 0.171468759323379 |
| Required trajectory judge | Not configured; deterministic scoring |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `086f401e40a692ae75c76ab35dc8d4456e62c28e27590a38b325ad90f3c38489` |
| Saved evaluation SHA-256 | `0a94907520f82e77a9f0be77890a775068b1bf4ae4600442c09b1d94392d3b6a` |
| Saved reward SHA-256 | `874dc58ff18b25cc7aea9fbf9ac5fc078f8d3a140c1fdbaca69a37bc53366a2b` |

The records are retained in the author's surrounding workspace under
`task_results/code-context-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261015T091230Z/jobs/2026-10-15__17-14-57/code-context-retrieval__DyAAf9t/verifier/evaluation.json` and
`task_results/code-context-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261015T091230Z/jobs/2026-10-15__17-14-57/code-context-retrieval__DyAAf9t/verifier/reward.json`. These are author-local evidence
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
