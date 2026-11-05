# Validation record

## 2026-11-05 repeated evidence judgments and runtime configuration

Each query still runs retrieval once. The verifier judges the resulting fixed evidence set three times and averages the three binary decisions; it then averages question scores across all twelve hidden queries. Invalid, empty, failed and timed-out retrievals remain zero without judge calls. Any failed judgment invalidates the measurement rather than averaging only successful calls. The separate trajectory audit still runs once. Reports retain all three decisions and their errors.

Evidence judging now requires `ANSWER_JUDGE_MODEL_NAME`, `ANSWER_JUDGE_BASE_URL` and `ANSWER_JUDGE_API_KEY` from the repository runtime configuration, passed only to the verifier. There is no fixed evidence-judge model or base URL and no fallback to solver credentials. The sufficiency prompt, effort `high`, temperature 0, hidden queries, references and public assets are unchanged.

The evidence-judge watchdog is 5,400 seconds. The budget estimate for 36 judgments on two workers is `18 * (2 * (10 + 120) + 2) = 4,716` seconds, including the existing two attempts and retry delay. Build, query-runner, evidence-judge and audit budgets total `2,400 + 1,860 + 5,400 + 3,600 = 13,260` seconds. The 14,400-second verifier limit leaves 1,140 seconds for termination grace, staging, cleanup and finalization. The 30-second per-query limit is unchanged.

The instruction now states that up to five queries may run concurrently. Its SHA-256 is `7b2eaf145937e085c44d38600af103243290977524192efc734844ee379b7a26`. Both environment documents use unwrapped prose. The resource document removes credential tutorials and duplicate links while preserving the exact solver API hosts and four allowed generative model IDs.

Completed locally:

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tasks/long-pdf-evidence/tests -p 'test_*.py' -v`: **27 passed**, including mixed three-round outcomes, fixed evidence inputs, a single failed round, configurable request routing, verifier-only settings and nested timeout budgets.
- `python scripts/validation/check_tasks.py tasks/long-pdf-evidence`: **0 errors**.
- `bash -n tasks/long-pdf-evidence/tests/test.sh` and task-scoped `git diff --check`: passed.
- The hidden query, reference and judge-prompt hashes still match the earlier fingerprints below; both environment documents have no wrapped prose, and the solver model allowlist is unchanged.

All judge responses in these tests were mocked. No live API evaluation, Docker build or new coding-model trial was run for this revision; no new retrieval score or semantic judge accuracy is claimed.

## 2026-10-28 semantic judge clarification — 1.0.0

Base: `bb0ddbaf105c25cc53e3598c37e0428c943a7098`.
This revision changes generic evidence-judge guidance and local validation
materials. The two PDF tasks use identical prompt text. It has no query IDs,
sentence IDs, character names or examples from scored questions.

All original questions, requirements, reference evidence, assets, executable
interfaces, model/effort settings, budgets and score aggregation are retained.
`instruction.md`, `raw-instruction.md`, `assets.json` and both hidden JSONL files
were compared byte-for-byte with the base revision and are unchanged.

| Fingerprint | SHA-256 |
| --- | --- |
| Agent instruction | `ac95ae6a38985cfdb57d6a259a77c90e9cb34e026ad2436b96f4f0648de5bd38` |
| Hidden queries | `7636e768d0876b0bb21620d799a871fa51b6a2f6a3a40c3444fddfa80482e5c6` |
| Hidden references | `fc819052f4c5e9f23338f5a689a7742d150bf3f99556627da48fe8ea7dbd829d` |
| SYSTEM_PROMPT text | `160e4740e8178004b4871692196d717b63d2a447b26fabe84dc407378ebe8b50` |

Completed locally with the existing `search_swe_cpu` Python environment:

- `python -B -m unittest discover -s tasks/long-pdf-evidence/tests -p 'test_*.py' -v`: **22 passed**. Includes mocked request transmission for all ten synthetic calibration cases, bounded malformed-response failure, and existing provenance, isolation and finalizer checks.
- `python scripts/validation/check_tasks.py tasks/long-pdf-evidence`: **0 errors**.
- `git diff --check`: passed.

The HTTP mock checks the production prompt and unmodified reference payload reach
the judge, and that author-supplied expected verdicts are not included in that payload.
Mocked verdicts do **not** validate semantic model accuracy.

`tests/judge_calibration.json` contains synthetic expected outcomes and rationales
for future live calibration. It is not read by production grading. Live judge
calibration, Docker builds and submission re-evaluation were not run, as requested.
The next evaluation must record the actual judge decisions against these cases
before treating the clarification as validated model behavior. Historical runs
retain their original versions and scores; no new model score is claimed here.
