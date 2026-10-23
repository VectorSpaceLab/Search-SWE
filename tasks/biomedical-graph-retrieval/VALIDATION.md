# Validation — version 0.2.2

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

## Public validation expansion — 2026-10-23

Five independently verified public examples are now installed in
`data/validation/queries.jsonl` and `ground_truth.jsonl`. The three v0.2.1
examples remain byte-identical at the beginning of both files, producing
**8 public queries and 20 unchanged hidden queries**. Metadata and both public
asset sizes/SHA-256 hashes match the installed data. Their remote revisions
remain unpublished, as before.

The additions cover target-set intersection/exclusion, distinct target support
counts, ordinary shortest-path unions, exclusive-target pathways, and ordered
protein-pair counts. Complete answer sizes are 2, 7, 4, 1 and 3. Python sets and
counts agree with independent SQLite queries; custom BFS agrees with NetworkX
shortest-path enumeration. New anchors differ from all old public/private anchors
and from each other. No complete answer set duplicates an existing example.
Other private query structures remain unexposed.

The graph, hidden files, both instruction files, verifier source, runtime limits
and environment files are unchanged by this update. A pre-existing update to
`raw-instruction.md` was preserved. The old v0.2.1 Luna reward 0 remains
historical evidence; no fresh coding-agent or online judge run has measured the
effect of the eight-example public set.

Author-only construction and installation evidence is in
`task_development/stark-prime-retrieval/public-additions-20261023/` in the
surrounding workspace, including `selected/author-evidence.jsonl`,
`verification.json`, `installation-before/` and `installation.json`.

Post-installation checks passed: all 25 task-local unit tests, production output
validation for all eight reference rows, and local size/SHA-256 verification of
all three assets. Byte comparison confirms that the original three rows were
preserved and the five additions exactly match the independently verified
candidates. Scoring the reference fixture returns 8/8; this is a scorer contract
check, not a model result. The static task check reports only the three existing
unpublished asset revisions (`revision: null`); publication pins remain pending.

## Archived v0.2.1 validation

The following sections describe v0.2.1 and the subsequent finalizer repair.
Statements about matching configuration and public assets refer to that revision.

Version 0.2.1 replaces the twenty public examples with three newly constructed
questions. Their query plans differ from all six private families: minimum
two-drug target cover, induced connected-component profiles, and deepest drug
synergy cores. Complete answer sets agree between separate Python/SQL or
Python/NetworkX calculations. Public query anchors do not overlap private query
anchors, and no public complete answer set equals a private complete answer set.
The twenty private questions and labels remain byte-identical to version 0.2.0.
Graph, scorer, instruction, executable interface and resource limits are unchanged.

The public examples are intended to require comparable reasoning and programming
effort without exposing private templates. This is a structural design judgment,
not measured coding-agent difficulty. The previous twenty public examples and
the rejected same-family draft remain outside the runtime task package.

## Completed v0.2.1 coding-agent trial

The existing author-side run was reconciled on 2026-10-22. Its saved summary
agrees with the original verifier evaluation and trial result. This supersedes
the earlier statement that no fresh v0.2.1 coding-agent result was available.

| Item | Recorded result |
| --- | --- |
| Trial ID | `biomedical-graph-retrieval__7iyRMF9` |
| Trial start / finish (UTC) | 2026-10-14 16:44:54.986566 / 18:14:56.809390 |
| Agent / harness | Codex 0.157.1 / Harbor 0.22.0 |
| Coding model / effort | OpenRouter `openai/gpt-6-luna` / `max` |
| Attempts / concurrency / retries | 1 / 1 / 0 |
| Configured resources | 16 CPUs, 32 GiB RAM, 100 GiB storage, no GPU |
| Budgets | Development 7,200 s; build 1,800 s; each query 30 s; verifier 5,400 s |
| Completion | Trial and verifier completed; launcher exit 0; no trial exception |
| Raw ExactSetAccuracy / final reward | 0/20 = 0.0 / 0.0 |
| Execution | Valid; no evaluation errors; 0 query timeouts; all 20 query commands exited 0 |
| Build / query timing | Build 21.694 s; query mean 10.616 s, maximum 23.295 s |
| Required trajectory judge | `deepseek/deepseek-v4.1-flash`; succeeded; numeric judgment 1; trajectory present |

The zero reward is a valid retrieval result: none of the twenty returned sets
exactly matched its reference. It was not caused by a failed audit, invalid
output or a query timeout. This single run does not establish universal
unsolvability or equal measured difficulty of the public and private splits.

The trial used a frozen working-tree snapshot; its saved metadata does not
identify a dedicated task commit. The following SHA-256 fingerprints bind the
instruction and grader to the recorded v0.2.1 snapshot:

| File | SHA-256 |
| --- | --- |
| `instruction.md` | `d5b276d357b2df5c1c664beeaee9fdf99b4116670b260d4437e744c40d548957` |
| `raw-instruction.md` | `8eca79e08a69568476627d06221cf837d67d04eece7ab2b55076550bfae4a482` |
| `tests/grader.py` | `143386613552fde5844cb6c09b4bf94cc13ff590d9ade82183e3483a179fec02` |

### Coverage of the finalizer repair

On 2026-10-22, `tests/finalize_reward.py` was hardened to accept only numeric
binary judgments and to record `judge_output_valid`; regression tests were added
in `tests/test_finalize_reward.py`. The trial above predates this repair. Its
finalizer SHA-256 was `4fe22c327f4f05057fbcb6e55e7847f8ec8c99448db5a35ce107a3477ec83bde`;
the repaired file is `25cf17acad337fb60685ead0b929b28e640a32725313489cb5dce71cc7406575`.
The instruction, task configuration, grader, hidden inputs, public asset manifest
and environment files match the saved snapshot. Documentation changes record
the evidence; the solver contract and deterministic metric are unchanged.

The task suite passed all **25 tests**, including six new finalizer tests, with
`python -B -m unittest discover -s tasks/biomedical-graph-retrieval/tests -p 'test_*.py' -q`.
An offline replay of the archived evaluation and saved numeric audit result
through the repaired finalizer preserved reward 0.0, with `judge_output_valid=true`
and the original trajectory present. This replay checks the final gate only;
neither the coding agent nor the online judge was run again.

### Original evidence locations

Paths below are relative to the surrounding author workspace, the parent of the
Search-SWE checkout. Evidence root:
`task_results/biomedical-graph-retrieval/codex-openrouter-gpt-6-luna-max-v021-20261014T164416Z/`.

- `REPORT.txt`, `evaluation-summary.json` and `run-config.json`: run summary,
  configuration and recorded model/effort.
- `snapshot/tasks/biomedical-graph-retrieval/`: exact pre-repair task snapshot.
- `jobs/2026-10-15__00-44-54/biomedical-graph-retrieval__7iyRMF9/`: original trial;
  contains `result.json`, `verifier/biomedical-graph-retrieval-eval/evaluation.json`,
  `verifier/reward.json`, `verifier/reward-details.json` and `agent/trajectory.json`.

These original files are local author-only evidence, not a published log bundle.
This document supplies the non-sensitive summary; a maintainer-accessible
redacted log handoff remains separate. Full trajectories, submitted code and
hidden evaluation inputs stay outside the public task package.

## Earlier-version evidence

The following model and runtime results concern earlier versions and are kept
separate from the completed v0.2.1 trial above.

The v0.1.1 full Codex/OpenRouter openai/gpt-6-luna max run scored 19/20
(0.95), with a passing trajectory audit. This supersedes the earlier fixed
per-query-baseline difficulty claim. Public examples exposed nearly all query
forms implemented by that submission.

Version 0.2.0 replaced all 20 private questions. At that revision, the complete
graph and both public validation files were unchanged. Scoring, budgets, API permissions,
container boundaries and executable interfaces are unchanged. The instruction
and structured source both clarify generalization beyond illustrative examples.

All 20 complete answer sets agree between independent computations (SQL joins
versus set enumeration, or NetworkX path algorithms versus custom BFS/counting).
Every question has recorded near misses and semantic review outside the task.
The new query/label files were frozen before evaluating the saved submission
or running a new Coding Agent.

Offline production-verifier checks completed: the author reference returned
20/20 exact sets (maximum query time 1.17 seconds), and the archived submission
returned 0/20 with valid output and no timeout. These checks had no audit API;
their deterministic accuracies are not final audited rewards. The saved replay
does not establish difficulty for a fresh Coding Agent.

At that earlier revision, a coding-agent attempt was stopped at the user's
instruction before submission or final scoring. That stopped attempt produced
no final score; the later completed v0.2.1 trial is recorded above. No additional
paid run was launched for this evidence reconciliation. The three unpublished
remote asset pins remain a separate release limitation.
