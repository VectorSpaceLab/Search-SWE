# Run evidence reconciled on 2026-11-05

The historical trial passed 1/10 complete table-and-join sets, with all ten outputs valid and within the deadline. It used deterministic coverage scoring without a compliance judge. The current revision retains that raw metric and adds a required compliance audit; it has no new coding-model result yet.

| Field | Observed value |
| --- | --- |
| Current package | `1.0.0` |
| Saved agent trial version | `0.6.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Historical available score | 0.1; current revision not model-evaluated |
| Raw metric | complete table-and-join coverage = 0.1 |
| Archived final reward | 0.1 |
| Required trajectory judge | Configured in current revision; not present in the historical trial |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Historical instruction SHA-256 | `ae454d3e90d118b3eaaf6c3e5965ba1e64d1610e233712c5778666a94b217680` |
| Current instruction SHA-256 | `88dca4daec63312dc1530d9030736998a8389669bd6ac589d5f979eb99d74a85` |
| Saved evaluation SHA-256 | `99efddb016378d5a8a912e8e589fda71f55257d58ef8e59e7ef200136a91029b` |
| Saved reward SHA-256 | `8f86c9e820010f98cf2d999e1c14d81982832bb2633e2b8414f88e7754b21fc7` |

The records are retained in the author's surrounding workspace under
`task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/harbor/2026-10-14__23-20-38/join-aware-table-retrieval__PkCnwyj/verifier/report.json` and
`task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/harbor/2026-10-14__23-20-38/join-aware-table-retrieval__PkCnwyj/verifier/reward.txt`. These are author-local evidence
locations, not public download links. Original trajectories, submitted code,
private evaluation outputs and credentials are not published in this task.
The current instruction, fixed evaluation order and compliance gate differ from
the historical evaluated revision. Do not report the archived reward as a
validated score for the current package.

The three public inputs have immutable source revisions, sizes and SHA-256 values
in `assets.json`, all at `search-swe/Search-SWE` revision
`2a2188f3a9426361da5f10c82a35148269574a92`. No assets were changed or republished
for this revision. This task has no model assets; source terms remain in
`LICENSE.data.md`.

Current local checks and their limits are recorded in `VALIDATION.md`. No new
coding-agent trial or paid judge call has run for this revision.
