# Run evidence reconciled on 2026-10-23

The build failed with PermissionError while the submission opened a hard-coded /tmp/court-search-*.log path. The verifier provides a writable index directory and TMPDIR. No query retrieval metric was measured; zero is the execution-failure penalty. The original result is preserved.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.2` |
| Saved agent trial version | `0.1.2` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0 |
| Raw metric | nDCG@10 = Not measured (build failed) |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Current instruction SHA-256 | `a41d40275ff625384a8b8a6d3ec422f605ace66693dd8424bc5c41bbfba7a056` |
| Saved evaluation SHA-256 | `d82a1c1b26f5b6573107efec81c6708bf422a1107373e70add3a26e2346e9c50` |
| Saved reward SHA-256 | `bb332babcb3415c07e4c5c775a4298aba3bd21c37feba0c313444cbe47862715` |

The records are retained in the author's surrounding workspace under
`task_results/legal-stance-retrieval/codex-openrouter-gpt-6-luna-max-v012-20261022T093112Z/jobs/2026-10-22__17-31-54/legal-stance-retrieval__5vakfpY/verifier/legal-stance-retrieval-eval/evaluation.json` and
`task_results/legal-stance-retrieval/codex-openrouter-gpt-6-luna-max-v012-20261022T093112Z/jobs/2026-10-22__17-31-54/legal-stance-retrieval__5vakfpY/verifier/reward.json`. These are author-local evidence
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
