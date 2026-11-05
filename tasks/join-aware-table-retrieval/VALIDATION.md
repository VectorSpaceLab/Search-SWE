# Validation — current package 1.0.0

Current revision (2026-11-05): the instruction is shorter, evaluation order is fixed, and the verifier now requires one compliance audit. The historical 0.6.0 coding trial below predates these changes; it is not evidence that the current audit has run. Public assets are pinned and unchanged. [RUN_RESULTS.md](RUN_RESULTS.md) separates historical results from current validation status.

## Current revision and local validation — 2026-11-05

The engineering objective, 10 public/10 hidden queries, complete-plan coverage metric, four allowed Qwen generation models, API hosts, hardware and candidate deadlines are unchanged. `grade.py` now preserves the frozen hidden query-file order. One independent trajectory/source audit gates the raw score; no answer-quality LLM judge or latency-scoring term was added. Audit credentials are verifier-only, and transferred trajectory files are protected before submitted code runs. Candidate commands retain access to the documented public API credentials.

Structural references: `tasks/biomedical-graph-retrieval` (CPU catalog-style retrieval with permitted external APIs and a separate integrity audit), `tasks/instruction-following-embedding` (separate raw-metric finalization and credential filtering), and the current `.agents/skills/create-searchswe-task` verifier templates. The checked-out reference revision was `783d2eeafd580f64c404da94dfc05733811d5c0f`; the neighboring instruction-following task also has session-local edits. The RewardKit backend and finalizer follow the current templates, with this task's own rubric, model allowlist and budgets. No neighboring task was modified for this change.

The instruction was reduced from 858 to 587 whitespace-separated words. Commands, JSON fields, response cardinality, byte/index limits, per-stage deadlines, public paths, complete-plan scoring and recovery behavior remain explicit. The rewrite removes solution suggestions, framework credential explanations and the benchmark source name; it adds the existing compute/development allocation and makes submission read-only access explicit. `raw-instruction.md` records these corrections, fixed ordering and the new integrity gate. Its pre-edit SHA-256 was `ff0bf8ab5798f1fa099e18a88e91311753bd0892c7c85814775b91b3adce5d99`.

`environment.md` now exactly matches `docker/cpu/environment.md`; the only addition was the template's Node.js/npm entry. `available_resources.md` retains the same words and permissions as `tasks/agentic-search`, with its wrapped prose paragraph joined. No agent-facing prose paragraphs have fixed-width line wrapping. All three public asset sizes/hashes match `assets.json`; no data was changed or republished.

| Budget | Limit and accounting |
| --- | --- |
| Candidate build | 1,200 s |
| Candidate query path | At most two 30 s startups, one 20 s warm-up and one 20 s scored request per question; 10 questions give at most 1,000 s before cleanup |
| Primary supervisor | 3,000 s, covering 2,200 s of candidate allowances plus cleanup and trusted overhead |
| Audit | One 1,200 s session inside a 1,500 s wrapper |
| Finalizer / outer verifier | 30 s / 4,800 s; 300 s beyond the two main wrappers covers finalization, termination grace and setup/cleanup |

Checks executed:

- `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tasks/join-aware-table-retrieval/tests -p 'test_*.py' -v`: 10 tests passed. These cover real public/hidden plan coverage and missing-table/join negatives, duplicate JSON keys, public-only credential forwarding, audit acceptance/rejection, missing trajectories, malformed/inconsistent audit details, timeout statuses and invalid metrics.
- `PYTHONDONTWRITEBYTECODE=1 python -B scripts/validation/check_tasks.py tasks/join-aware-table-retrieval --merge-ready`: zero errors. `bash -n`, Python parsing, both Compose-overlay checks and scoped `git diff --check` also passed.
- `docker build -t search-swe-local:bingyu-join-verifier-20261105 tasks/join-aware-table-retrieval/tests`: passed. The first download from the default Python index stalled and was interrupted; the task Dockerfile now uses the same Tsinghua package mirror used by other verifier images. The final image has RewardKit 0.2.0, LiteLLM 1.97.0 and Codex 0.164.0; its Node.js/npm versions match the public template. RewardKit CLI/rubric loading passed with networking disabled.
- `python -B /tmp/bingyu-join-audit-20261105-2p6az7kq/run_checks.py`: 14 disposable-container checks passed with `--network none`, synthetic catalog/query fixtures and an offline audit backend. Cases cover acceptance and repeat-order consistency, rejection, simulated judge-timeout exit, malformed and inconsistent decisions, missing credentials/trajectory/corpus, failed build, missing joins, invalid outputs, query timeout and warm-up recovery. An invoked audit ran exactly once. Candidate code could read public API variables and use scratch space but could not read hidden labels, verifier logs or trajectory evidence, modify submission source, or access judge variables. Results and the reproduction script are author-local temporary evidence at `/tmp/bingyu-join-audit-20261105-2p6az7kq/results.json` and the adjacent `run_checks.py`/`container_check.py`; they are not published assets.

The container checks use fabricated protocol fixtures and stubbed audit decisions. They verify execution, isolation and finalization, not retrieval quality or a real judge's policy decisions. The query-timeout fixture shortens only its disposable copy's deadline; the packaged deadline remains 20 seconds. No live judge request or fresh coding-agent trial was authorized or executed for this revision. The unchanged agent Dockerfile was not rebuilt. Current real-model score and live audit health remain unmeasured; the historical 0.1 result below does not close that validation gap.

| Current file | SHA-256 |
| --- | --- |
| `instruction.md` | `88dca4daec63312dc1530d9030736998a8389669bd6ac589d5f979eb99d74a85` |
| `raw-instruction.md` | `f8ccaf03d40b491b902bc294a87bfab9b23f45f385d34da3211e27af8db3eb43` |
| `task.toml` | `370377b87515671d9369fbb878a395e0178c71c91030773385e16cde82d07f7f` |
| `tests/grade.py` | `d9f8ee029943e6464d3c95e4bb6b0c126a5616c8a9364684125e78f2c8560019` |

## Historical evidence reconciliation — 2026-10-22

This record reconciles the existing final-package coding-agent trial on
2026-10-22. It does not launch a new trial. Retrospective subset replays and
earlier validation sets remain separately described in [README.md](README.md).

## Historical completed trial — version 0.6.0

| Item | Recorded result |
| --- | --- |
| Trial ID | `join-aware-table-retrieval__PkCnwyj` |
| Trial start / finish (UTC) | 2026-10-14 15:20:38.689378 / 16:21:36.192321 |
| Agent | Codex 0.157.1 through OpenRouter |
| Coding model / effort | `openai/gpt-6-luna` / `max`; effective model and effort checked in the saved run record |
| Attempts / concurrency / retries | 1 / 1 / 0 |
| Configured resources | 16 CPUs, 32 GiB RAM, 100 GiB storage, no GPU |
| Budgets | Development 7,200 s; build 1,200 s; readiness 30 s; each scored response 20 s; verifier 4,800 s |
| Completion | Trial and verifier completed; no trial exception; launcher exit 0 |
| Raw complete-plan success / final reward | 1/10 = 0.1 / 0.1 |
| Output validity / failures | 10/10 valid; 0 query timeouts, warm-up failures or recorded query errors |
| Build / query timing | Build 0.307 s; query mean 3.736 s, maximum 5.257 s |
| Failure analysis | Eight answers lacked a necessary table; one covered the tables but missed a required relationship |
| Judge status | Not applicable: deterministic complete table-and-join coverage; no model judge |

The low score reflects valid returned predictions failing the required plan
coverage, rather than invalid outputs or enforced query timeouts. Server stderr
was empty, but raw HTTP responses were not captured. This establishes absence of
logged API failures, not independent verification of each API response. The
coding-agent development self-tests reported 10/10 online and offline; their raw
predictions were not saved and their checker did not enforce the 20-second
deadline, so they are not an independent formal validation replay.

## Historical revision coverage

The trial's `run-metadata.json` contains a 24-file SHA-256 manifest. All 23 files
other than `README.md` matched the package at the 2026-10-22 reconciliation. The
README had been updated after the trial to report its result. The fingerprints
below identify that historical evaluated revision, not the current working tree.

| File | SHA-256 |
| --- | --- |
| `instruction.md` | `ae454d3e90d118b3eaaf6c3e5965ba1e64d1610e233712c5778666a94b217680` |
| `raw-instruction.md` | `ff0bf8ab5798f1fa099e18a88e91311753bd0892c7c85814775b91b3adce5d99` |
| `task.toml` | `efdcf4d87ffcd3f30cb2ed87591f24274bbad13b3be85255d1912bd7f25df47a` |
| `tests/grade.py` | `1c0abcfc5b54f057564af03d521b47cf4a4a1fe5ac906a89f3f83973eebdb1fc` |

The run record identifies the evaluated working-tree package by these frozen
fingerprints, not a dedicated final task commit. No commit is invented for this
documentation update.

## Original evidence locations and remaining limits

Paths are relative to the surrounding author workspace, the parent of the
Search-SWE checkout. Evidence root:
`task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/`.

- `REPORT.txt`, `evaluation-summary.json` and `query-results.json`: aggregate
  result, per-query metrics, timings and coverage-based failure categories.
- `run-metadata.json` and `post-evaluation-package-check.json`: model/effort,
  frozen file hashes, completion and documentation-only post-trial changes.
- `harbor/2026-10-14__23-20-38/join-aware-table-retrieval__PkCnwyj/`:
  original `result.json`, `verifier/report.json`, reward and trajectory artifacts.
- `source-audit.json` and `validation-development-results.json`: recorded
  submission review and development-self-test limits.

The trial and original evidence remain local and author-only. This document
provides a non-sensitive summary; the paths above are not a published log
bundle. A maintainer-accessible redacted log handoff remains separate. Full
submissions, trajectories and hidden evaluation inputs are not added to the
public task package. All three public asset entries now have immutable revision
`2a2188f3a9426361da5f10c82a35148269574a92`, exact sizes and SHA-256 hashes.
