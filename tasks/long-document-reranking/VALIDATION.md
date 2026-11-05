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
- `python scripts/validation/check_tasks.py tasks/long-document-reranking`: 0 errors.
- `bash -n tasks/long-document-reranking/tests/test.sh`: passed.
- `git diff --check -- tasks/long-document-reranking`: passed.

No image build, model/API call, coding rerun or archived-submission reevaluation
was performed. Runtime validation is deferred to the follow-up evaluation agent;
the local regressions do not establish actual reranker service performance.

## 2026-11-05 audit consistency and documentation corrections

Scope: the audit-result gate, offline compliance rubric, filename-based false positives and agent-facing documentation. The existing PID cleanup, two sequential query invocations, first-invocation Accuracy@5 scoring, stage timeouts, outer verifier budget, resources, candidate pools and fixed model are unchanged.

The finalizer now requires a complete, consistent binary audit result: the aggregate, group score, raw criterion and normalized value must agree, with a non-empty judge output and no reported group or criterion errors. A valid rejection gives zero reward without an infrastructure error. Incomplete, contradictory, nonbinary, malformed or unsuccessful audits give zero reward and exit status 1. The existing test.sh propagates that status. Reward files retain their numeric schema, with health diagnostics in reward-details.json.

The offline audit rubric no longer permits downloading dependencies or models. The grader no longer treats .bin, .pt or other filename extensions as proof of extra model weights; the compliance audit checks actual contents and use while retaining the unchanged-model requirement. The output contract now explicitly requires input query order. Instructions use /path/to/index, allow the result file at the supplied --output path, and omit framework names and the internal total-budget breakdown. Agent-visible Markdown paragraphs are unwrapped. The structured instruction source has matching interface and scoring conditions; detailed verifier budgets remain in task.toml and the maintainer README.

Read-only structural precedent: tasks/legal-stance-retrieval/tests/finalize_reward.py for binary audit consistency and the distinction between a rejected audit and an infrastructure failure. Its metric, normalization, repeated-timing implementation and task-specific constraints were not transferred. The expected reward-details.json layout was checked against the locally installed RewardKit 0.2.0 serializer.

Checks on this revision:

- `python -B -m unittest discover -s tasks/long-document-reranking/tests -p 'test_*.py' -v`: 19 tests passed. These cover fractional accepted scores, valid rejections, missing/malformed/contradictory/nonbinary audit results, reported audit errors, failed judge processes, missing trajectories, invalid execution, ordinary files with model-like extensions, query ordering and the existing two-invocation behavior.
- `python -B scripts/validation/check_tasks.py tasks/long-document-reranking --merge-ready`: 0 errors.
- `bash -n tasks/long-document-reranking/tests/test.sh tasks/long-document-reranking/environment/starter/build.sh tasks/long-document-reranking/environment/starter/run.sh`: passed.
- `git diff --check -- tasks/long-document-reranking`: passed.
- Compared with HEAD: the PID cleanup, command execution and output-validation functions are unchanged; task.toml, test.sh, Docker/Compose files, assets.json, hidden queries/labels and starter execution code are unchanged. Agent-visible instruction/docs/starter README contain no fixed-width paragraph wrapping.

Validated file SHA-256 values:

| File | SHA-256 |
| --- | --- |
| instruction.md | adafe2499214172aeab6585e922634a1ae1470c1512556a6d24d5589917c1d3b |
| raw-instruction.md | 47fb281889fac69cca16f7112117dda6c1e13223e5f5d742e81e6d9a1feaad16 |
| tests/grader.py | 9cfeba45d93b4086eb11a43e545cd02fcffcad1f8d9cdef8e0e1c0eae5ff2c6b |
| tests/finalize_reward.py | 7495d884ca2cdcf2eadcdc7666a2085c55680ebdf2ed67587c744c7e4df378c0 |
| tests/jailbreak_judge/codex.toml | 747883c7482f4b5b71334bf2ee3ef488f96ae7b5b1a8c2be17a4f7f9ce483e4c |

No model/API call, image build or full task evaluation was run for this revision. The public data and model assets were not installed in this checkout. These offline checks establish the edited gate and contract behavior, not actual reranker performance or live judge availability.
