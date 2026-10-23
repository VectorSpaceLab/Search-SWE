# Run evidence reconciled on 2026-10-23

The original v0.3.0 attempt encountered Docker infrastructure failure. A verifier-only rerun of its saved submission and original trajectory completed, with valid retrieval and a passing audit, scoring 1/10. This is not a newly generated agent solution.

| Field | Observed value |
| --- | --- |
| Current package | `0.3.0` |
| Saved agent trial version | `0.3.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0.1 |
| Raw metric | Accuracy@1 = 0.1 |
| Archived final reward | 0.1 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 4 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `03a445f6f0bfa8ab8bd51a0ca788a4d1da15190939d2a76c6bd49b39aec0a16c` |
| Saved evaluation SHA-256 | `ba4ab28e915216cb940a20d6d792525d92aa8ea0c6b5fd73623871d22233cd9b` |
| Saved reward SHA-256 | `7ec2c8c73e237464e690ceececf5f33b3533a5c95ba7d30750f4764b9fea91ba` |

The records are retained in the author's surrounding workspace under
`task_results/negative-constraint-retrieval/codex-openrouter-gpt-6-luna-max-v030-20261022T070131Z/regrade-20261022-infra3/trials/negative-constraint-retrieval__regrade3/verifier/negative-constraint-retrieval-eval/evaluation.json` and
`task_results/negative-constraint-retrieval/codex-openrouter-gpt-6-luna-max-v030-20261022T070131Z/regrade-20261022-infra3/trials/negative-constraint-retrieval__regrade3/verifier/reward.json`. These are author-local evidence
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
