# Validation — version 0.6.0

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

This record reconciles the existing final-package coding-agent trial on
2026-10-22. It does not launch a new trial. Retrospective subset replays and
earlier validation sets remain separately described in [README.md](README.md).

## Completed final-package trial

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

## Revision coverage

The trial's `run-metadata.json` contains a 24-file SHA-256 manifest. All 23 files
other than `README.md` matched the current package during reconciliation. The
README had been updated after the trial to report its result. This update adds
the present validation record and its README link; task configuration, runtime,
instructions, public assets and hidden inputs remain unchanged. No repeat
coding-agent evaluation is needed merely to consolidate this evidence.

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
public task package. The local asset manifest still has three null remote
revision pins; this evidence update does not claim remote reproducibility or
resolve publication status.
