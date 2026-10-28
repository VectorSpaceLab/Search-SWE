# Local validation

## Reference-label correction — 2026-10-28, version 1.0.0

Removed only `include/nlohmann/detail/meta/type_traits.hpp:1–5` from the `test-009` reference regions. These five lines contain a project banner, version and URL; they do not implement unsigned-enum serialization. The other four regions remain unchanged, reducing the reference set from 206 to 201 distinct physical lines. All 20 hidden queries remain in the test set.

- Compared the packaged labels against the previous Git revision: only this region changed; the other 19 reference rows are byte-identical. Query text, source files, task metadata, grader and scoring formula are unchanged.
- Loaded the complete repository corpus with the production scorer and validated all 20 reference outputs: every output satisfies the five-region/500-line contract, stays within actual file bounds and scores F1 = 1 against its current labels.
- Scored a synthetic output containing the four retained regions: the old labels gave F1 = 0.9877149877149877; the corrected labels give F1 = 1. This is a scorer check, not an agent result.
- All eight existing scoring contract tests passed. `python scripts/check_tasks.py tasks/code-context-retrieval` reported zero errors.

Historical model and baseline scores below and in `RUN_RESULTS.md` use the earlier labels; they have not been recomputed. No new agent or model run was performed. Scoring remains direct mean line F1, so no baseline normalization constant requires updating.

## Archived validation, version 0.1.0

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

The current package uses real source directories under `data/repos/<snapshot_id>/`.
It has passed local grader and corpus-based retrieval checks. A real coding-agent
trial reached the development time limit and then completed verifier scoring;
its result and exception are recorded below. The package remains unpublished.

Instruction SHA-256: `086f401e40a692ae75c76ab35dc8d4456e62c28e27590a38b325ad90f3c38489`. Structured source SHA-256: `66ca51504312e7443c8d2eb58d82cce07e4493afaf8b58514f3811dd7e6dcba6`. Grader SHA-256: `c3252d804b9ccf47c3e24a470baa35fe523989ad78156a64ff3514c9add213ca`. Scorer SHA-256: `2db20cec9e79fc0c54a7d9cccbf6edde40184f7e97c72c59baf8992736739823`. The full package inventory is in `task_development/code-bug-localization/package-build/package-hashes.json`.

## Coding-agent trial with development timeout

Existing run evidence was reconciled on 2026-10-22. The summary agrees with the
original trial result and verifier evaluation. Before these documentation edits,
all 19 compared configuration, instruction, manifest, environment, test and
documentation files matched the saved task snapshot byte-for-byte. Runtime
files and the instruction remain unchanged.

| Item | Recorded result |
| --- | --- |
| Trial ID | `code-context-retrieval__DyAAf9t` |
| Trial start / finish (UTC) | 2026-10-15 09:14:57.244833 / 11:22:25.957511 |
| Agent / harness | Codex 0.157.1 / Harbor 0.22.0 |
| Coding model / effort | OpenRouter `openai/gpt-6-luna` / `max`; launch model and effort flags verified |
| Configured resources | 16 CPUs, 32 GiB RAM, 100 GiB storage, no GPU |
| Budgets | Development 7,200 s; build 3,600 s; each query 180 s; verifier 7,800 s |
| Agent completion | `AgentTimeoutError`: agent execution timed out after 7,200 s |
| Verifier completion | All 20 queries scored; valid fraction 1.0 |
| Raw mean line F1 / final reward | 0.17146875932337885 / 0.17146875932337885 |
| Query outcomes | 10 nonzero-F1 answers; no perfect-F1 answers; 0 invalid outputs, nonzero exits or query timeouts |
| Build / query timing | Build 69.318 s; query mean 12.957 s, maximum 22.307 s |
| Judge status | Not applicable: deterministic line F1; no answer or trajectory model judge |

Launcher exit 0 does not remove the recorded agent exception. The saved run
summary retains `status=needs_inspection`. The reward measures the submission
that existed when the development budget expired, and is retained as a real
CPU/API measurement. It is not evidence of an exception-free coding-agent run.
The reason the agent used its entire budget was not established by this evidence
reconciliation. Inspect the trajectory before deciding whether an additional
trial is needed; no timeout, scoring or resource limit was changed.

The original `run-config.json` records source checkout HEAD
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8`. This is the authoring baseline, not a
commit containing this then-untracked task. The frozen snapshot and instruction,
grader and scorer SHA-256 values above identify the evaluated package.
The earlier local GPU screening remains separate from this CPU/API trial.
There is no independent per-request API-health audit or model-based compliance
verdict implied by the valid line-F1 score.

### Original evidence locations

Paths are relative to the surrounding author workspace, the parent of this
checkout. Evidence root:
`task_results/code-context-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261015T091230Z/`.

- `REPORT.txt`, `evaluation-summary.json`, `run-config.json` and
  `observed-launch.json`: result, exception, resource configuration and launch verification.
- `snapshot/tasks/code-context-retrieval/`: evaluated task files.
- `jobs/2026-10-15__17-14-57/code-context-retrieval__DyAAf9t/`: original trial;
  `result.json` retains the timeout, `verifier/evaluation.json` contains every
  query's F1, validity and timing, and `verifier/reward.json` contains the reward.
  The original coding trajectory is `agent/trajectory.json` within that trial.

Original logs, predictions, submitted code and trajectories remain author-only.
This document is the non-sensitive evidence summary; the local paths are not a
published log bundle. A maintainer-accessible redacted handoff remains separate.

## Checks on the current directory layout

- Compared all 51,920 files against both the previous JSONL and the pinned file inventory: all 324,317,309 source bytes and all physical line counts are unchanged. All 30 original issue texts and gold region sets are unchanged. Every reference output remains legal and scores one.
- Confirmed 30 anonymous snapshot root names, each query's explicit snapshot scope, and disjoint validation/test snapshots. Internal file paths, source contents and issue text are preserved; this does not claim that project identities cannot be inferred from those contents.
- Verified all 51,922 public asset files, including the two validation files, against their sizes and SHA-256 hashes. Local staged release validation with `allow_unpublished=True` passes. The checker was run with process-local `core.quotepath=false` so six original Unicode filenames are compared correctly; no Git configuration or filenames were changed.
- Parsed both Compose overlays and checked every mounted source. The agent container exposed the repository directories, ten validation questions and docs as read-only. Hidden labels, the author-side source mapping and GPUs were absent.
- Ran eight scorer regression tests, including physical newlines, identical paths in different snapshots and rejection of source symlinks. The source line matching and F1 formula are unchanged.
- Built `search-swe-local:code-context-retrieval-verifier-repos-v010` from the standard CPU image. The unchanged agent image was reused for the mount checks. Ran the following author-only fixtures in fresh containers with network disabled, 16 CPU cores, 32 GiB RAM, no GPU and submission UID 10001 through the real build/run interface.

| Author-only fixture | Expected reward | Observed reward |
| --- | ---: | ---: |
| Complete-gold oracle | 1.0 | 1.0 |
| Malformed/invalid outputs and isolation probes | 0.0 | 0.0 |
| BM25 indexing and retrieval from `repos/` | 0.1050217889 | 0.1050217889 |

The directory-based BM25 fixture built in 106.55 seconds; its slowest query invocation took 0.37 seconds. Its score exactly matches the previous corpus-based pilot. It has no hidden labels. The oracle and invalid-output fixtures deliberately contain author-side reference material and validate the grader; they are not legitimate search implementations or coding-agent trials. No fixture is supplied in the task.

The negative fixture processes all 20 questions and checks malformed JSON, duplicate fields, nonfinite numbers, invalid Unicode, unknown paths, bad bounds, wrong IDs, excess regions/lines, process errors, symlinks and FIFOs. Its permission probe confirms that submitted code cannot read hidden labels or the grader, rewrite rewards/reports or submitted code, or write source files in the mounted `repos/` tree.

## Retained earlier evidence

The previous package and evidence are retained under `package-build/before-repos-layout/`. Earlier checks covered build failure, a real 180-second timeout with the remaining 19 questions scored, 2,970 pilot metric comparisons, and repository integration tests. The timeout/supervision and F1 calculation are unchanged; those checks were not repeated for this input-layout change. The current layout was separately validated with the oracle, negatives and actual BM25 retrieval above.

Structural precedents remain `tasks/reasoning-query-rewriting` and `tasks/agentic-search` at base `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`. The standard CPU/API docs and policy are unchanged. User-requested CLI examples are retained. Development remains 7,200 seconds, build 3,600 seconds and each query 180 seconds.

## Remaining layers

The recorded coding-agent trial and completed verifier replace the earlier
statement that no coding-agent run had occurred. A clean agent completion is
still not established, and the development timeout remains an explicit limit
of this evidence. No new coding-agent or paid-API run was performed for this
documentation update. The local manifest revisions remain `null`, so strict
release checks still require real publication pins; remote reproducibility or
release-ready status is not claimed.

Author-side evidence: `task_development/code-bug-localization/package-build/repos-layout-verification.json`, `repos-static-check.json`, `repos-staged-release-check.json`, `repos-agent-environment-check.json`, `repos-runtime-summary.json` and `runtime/repos-*/`.
