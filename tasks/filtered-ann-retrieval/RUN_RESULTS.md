# Run evidence reconciled on 2026-10-23

The archived v0.10.1 full trial scored 1.0 with a successful passing audit. Version 0.11.0 has 10 public and 25 hidden queries. Five replays of the saved program each passed 5/25 within 15 ms (0.20); all answers were correct, but twenty per replay were late. These are saved-program retrieval measurements, not a new full verifier reward. The reference maximum was 14.985 ms, so timing stability and a fresh full trial remain open validation work.

Version 0.11.1 closes System V IPC persistence across verifier phases. Its
instruction, data, scoring formula and deadlines are unchanged. The 0.20 replay
below belongs to v0.11.0; no new Luna score or live audit was produced by this
fix. All 22 grader tests and the actual subprocess recovery/failure checks pass;
see [VALIDATION.md](VALIDATION.md) for their scope.

| Field | Observed value |
| --- | --- |
| Current package | `0.11.1` |
| Saved agent trial version | `0.10.1` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved-program replay on the revised split; not a new final reward |
| Latest available score | 0.2 (v0.11.0 saved-program replay) |
| Raw metric | exact Top-10 AND <=15ms pass rate = 0.2 |
| Archived final reward | 1 |
| Required trajectory judge | Succeeded; numeric pass = 1 in the old v0.10.1 trial; not rerun for v0.11.0 or v0.11.1 |
| Current CPU / RAM / GPU configuration | 8 CPUs / 16384 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `1ac4215f055a528982c01420d85ffff6f683774304e7aa45db19a6d438da5260` |
| Saved evaluation SHA-256 | `09beec6c18f6132da6ae38bb0afe0e87074f9e415f6ba0e0f7d27302666cc502` |
| Saved reward SHA-256 | `d11f71be21ecbebee608e04e05e277a2ce2e5cc93fc08912f3e50323473cfbff` |

The records are retained in the author's surrounding workspace under
`task_results/filtered-ann-retrieval/codex-openrouter-gpt-6-luna-max-v0101-20261022T135859Z/jobs/2026-10-22__21-59-35/filtered-ann-retrieval__fvGoMji/verifier/filtered-ann-retrieval-eval/evaluation.json` and
`task_results/filtered-ann-retrieval/codex-openrouter-gpt-6-luna-max-v0101-20261022T135859Z/jobs/2026-10-22__21-59-35/filtered-ann-retrieval__fvGoMji/verifier/reward.json`. These are author-local evidence
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
