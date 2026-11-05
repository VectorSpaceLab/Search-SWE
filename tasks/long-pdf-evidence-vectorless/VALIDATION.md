# Validation record

## 2026-11-05 repeated evidence judgments and runtime configuration

Retrieval still runs once per query. The verifier judges the fixed returned evidence three times, averages those binary judgments per query, then averages across all twelve hidden queries. Invalid, empty, failed and timed-out retrievals remain zero without judge calls. Any failed judgment invalidates the measurement instead of averaging only successful calls. The separate trajectory audit remains one run. All three decisions and errors are retained in the evaluation report.

Evidence judging requires `ANSWER_JUDGE_MODEL_NAME`, `ANSWER_JUDGE_BASE_URL` and `ANSWER_JUDGE_API_KEY` from runtime configuration, passed only to the verifier. There is no fixed evidence-judge model or base URL and no fallback to solver credentials. The evidence sufficiency prompt, effort `high`, temperature 0, hidden queries, reference evidence, asset manifest, embedding prohibition and index-only search boundary are unchanged.

The evidence-judge limit is 5,400 seconds. The request-budget estimate is `18 * (2 * (10 + 120) + 2) = 4,716` seconds for 36 judgments on two workers, including bounded retries. Build, query-runner, evidence-judge and trajectory-audit budgets total `2,400 + 1,860 + 5,400 + 3,600 = 13,260` seconds. The 14,400-second verifier limit leaves 1,140 seconds for termination grace, staging, cleanup and finalization. The 900-second per-query and 1,800-second shared query limits are unchanged.

Both environment documents only merge wrapped prose; all wording, links, code blocks and permissions are preserved. The instruction's evidence criteria omit judge model, request parameters, worker count, retries and judge-stage budgets. Its SHA-256 is `b403fe9bc0fff3e635e8ffe88d3abcb09e71f8f38386fa9f69d053cda316ba7d`.

Completed locally:

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tasks/long-pdf-evidence-vectorless/tests -p 'test_*.py' -v`: **27 passed**, including mixed three-round averages, fixed evidence inputs, a single failed round, runtime configuration, nested timeout budgets and the existing corpus permission boundary checks.
- `python scripts/validation/check_tasks.py tasks/long-pdf-evidence-vectorless`: **0 errors**.
- `bash -n tasks/long-pdf-evidence-vectorless/tests/test.sh` and task-scoped `git diff --check`: passed.
- Both environment documents are identical to their prior contents after whitespace normalization, with code blocks unchanged. Hidden query, reference and judge-prompt hashes still match the historical fingerprints below.

Judge responses were mocked. No live API evaluation, Docker build or new coding-model trial was run, and no new task score is claimed. The four public assets are not restored in this checkout; use the existing asset manifest to restore them before a full evaluation.

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
| Agent instruction | `dca96316ded3c3dbb3aa3eb377ca8494e416d536bce20b644149aef8bdd29fb8` |
| Hidden queries | `7636e768d0876b0bb21620d799a871fa51b6a2f6a3a40c3444fddfa80482e5c6` |
| Hidden references | `fc819052f4c5e9f23338f5a689a7742d150bf3f99556627da48fe8ea7dbd829d` |
| SYSTEM_PROMPT text | `160e4740e8178004b4871692196d717b63d2a447b26fabe84dc407378ebe8b50` |

Completed locally with the existing `search_swe_cpu` Python environment:

- `python -B -m unittest discover -s tasks/long-pdf-evidence-vectorless/tests -p 'test_*.py' -v`: **22 passed**. Includes mocked request transmission for all ten synthetic calibration cases, bounded malformed-response failure, and existing provenance, isolation and finalizer checks.
- `python scripts/validation/check_tasks.py tasks/long-pdf-evidence-vectorless`: **0 errors**.
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
