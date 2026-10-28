# Long-document Reranking Validation

## 2026-10-28 verifier validation — 1.0.0

Base: `bb0ddbaf105c25cc53e3598c37e0428c943a7098`.
This is a correction to the existing task; its CPU runtime, fixed inputs/model,
candidate pool, output rules, integrity audit and Accuracy@5 metric are retained.
No other task package supplies implementation or scoring parameters.

The verifier now validates both query invocations independently. Different JSON
formatting, scores or valid rankings do not fail the repeat check. The first
invocation still determines retrieval quality; an invalid second output or
failed second invocation still invalidates the submission.

`raw-instruction.md` and `instruction.md` now both disclose the existing build
limit, two sequential full-query invocations, per-invocation limit, first-run
scoring and total verifier allowance. Their commands, inputs, output cardinality,
candidate restrictions and model restrictions are unchanged.

Instruction SHA-256: base `1c1feabe2bc02467bde9b000e868550852809d37c5c1216f8a8e6371871046a0`;
revision `7db28542a20d4cc83a87801a2b239ae60ebaff86bee4021af409c4e5b13cb04c`.

| Stage | Seconds |
| --- | ---: |
| Submission build | 1800 |
| Two query invocations | 2 × 3600 |
| Trajectory judge | 3600 |
| Setup and cleanup | 600 |
| Outer verifier | 13200 |

The outer allowance was already 13200 in the base revision and remains unchanged.

Local checks used the existing `search_swe_cpu` Python environment:

- `python -m unittest discover -s tasks/long-document-reranking/tests -p 'test_*.py' -v`: 8 tests passed. Temporary synthetic fixtures exercise the real grader with mocked submission execution: valid formatting/score/ranking differences, unchanged first-run quality, invalid first or second output, missing query coverage, invalid IDs/counts/scores/order, malformed JSON, command failure, cleanup and budget coverage.
- `python scripts/check_tasks.py tasks/long-document-reranking`: 0 errors.
- `bash -n tasks/long-document-reranking/tests/test.sh`: passed.
- `git diff --check -- tasks/long-document-reranking`: passed.

No image build, model/API call, coding rerun or archived-submission reevaluation
was performed. Runtime validation is deferred to the follow-up evaluation agent;
the local regressions do not establish actual reranker service performance.
