# Validation record

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
- `python scripts/check_tasks.py tasks/long-pdf-evidence`: **0 errors**.
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
