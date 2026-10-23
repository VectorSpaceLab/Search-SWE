# Run evidence reconciled on 2026-10-23

The v0.1.1 verifier completed all eight queries with valid outputs, no query timeouts and a passing audit, scoring 0/8. This is a valid low retrieval score. A compliant positive-result reference under the final runtime contract and independent label/alternative-answer review remain validation gaps.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.1` |
| Saved agent trial version | `0.1.1` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0 |
| Raw metric | Accuracy@1 = 0 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `6dbf8e9b1226419e87c86524368e6d459b0fc2661dc361d0daaca57f0b70e440` |
| Saved evaluation SHA-256 | `b8eab2a81b24b5e7af92c5802fed7934b40a3b423becc084ed51ad3e04f19ad2` |
| Saved reward SHA-256 | `e51c8aa464a110f769a86cc20898314713b79b8d93a77a325a34684b994d6aaf` |

The records are retained in the author's surrounding workspace under
`task_results/paper-metadata-retrieval/codex-openrouter-gpt-6-luna-max-v011-20261022T093112Z/jobs/2026-10-22__17-31-54/paper-metadata-retrieval__te9Wvwy/verifier/paper-metadata-retrieval-eval/evaluation.json` and
`task_results/paper-metadata-retrieval/codex-openrouter-gpt-6-luna-max-v011-20261022T093112Z/jobs/2026-10-22__17-31-54/paper-metadata-retrieval__te9Wvwy/verifier/reward.json`. These are author-local evidence
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
