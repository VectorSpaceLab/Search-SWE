# New-task verifier layout and contract

Every new package has a task metric and a separate trajectory integrity audit.
The metric measures the engineering result; the audit checks compliance with
the actual task constraints. A subjective answer judge, when needed, is another
task-specific component.

The scaffolder's `assets/task/` templates generate:

| File | Responsibility |
| --- | --- |
| `tests/test.sh` | Initialize zero reward, supervise phases, clean candidate processes, retain logs and propagate measurement failures |
| `tests/grader.py` | Validate fixed inputs, execute confined submission code, enforce stage/resource limits and produce `report.json` |
| `tests/jailbreak_judge/codex.toml` | Task-specific integrity rubric and bounded judge session |
| `tests/rewardkit_deepseek.py` | Pinned RewardKit/Codex integration for the trajectory audit |
| `tests/finalize_reward.py` | Combine the metric with an actual healthy audit; emit reward and measurement health |
| `VALIDATION.md` | Author-facing design, checks, model feedback, revisions and final evidence |

The verifier image copies only the audit rubric to `/audit`, which is the
RewardKit discovery root. Grader code stays under `/tests`; the evaluated agent
does not receive either directory or `VALIDATION.md`. Preserve a small,
self-contained layout and add helper modules only as the task needs them.
Existing packages may retain their original grader/report filenames.

## Complete the grader and rubric

The generated grader deliberately reports an infrastructure error until the
task is implemented. Add the actual metric, input checks, submission interface,
unprivileged execution, clean child environment, time/resource accounting and
known-good/negative tests. Create a submission-writable work directory and keep
hidden inputs, trajectory, grader, logs and reward files root-owned and outside
that directory. Declaring UID 10001 in the image does not itself confine code.

Write the task's actual inputs, permitted changes, models/APIs, output contract
and prohibited circumvention in the audit rubric. Keep ordinary bugs and low
quality separate from misconduct. Judge credentials are mapped only into the
verifier; candidate commands receive a filtered environment without them.
The generated default uses RewardKit 0.2.0 with Codex pinned from the target
checkout and `deepseek/deepseek-v4.1-flash` via OpenRouter. Validate a changed
backend/model before use. Configure `VERIFIER_OPENAI_BASE_URL` and
`VERIFIER_OPENAI_API_KEY` locally; follow the missing-key handoff in
[model-evaluation.md](model-evaluation.md).

## Primary report and final outcome

Write `/logs/verifier/report.json` with a finite numeric `reward` in `[0, 1]`,
boolean `valid`, and one of these `status` values:

| Status | `valid` | Reward | Primary process exit |
| --- | --- | --- | --- |
| `ok` | `true` | Actual metric, including a valid zero | 0 |
| `submission_failed` | `false` | 0; candidate violated a documented gate/limit | 0 |
| `infrastructure_error` | `false` | 0; inputs, trusted verifier or services failed | Nonzero |

Retain task-specific metrics and explicit error/phase diagnostics alongside
these fields. The supervisor timeout is a trusted measurement failure; enforce
candidate deadlines inside the grader so they can be reported as candidate
violations and cleaned before the overall supervisor expires.

RewardKit writes a folder aggregate to `judge.json` and its criterion details
to sibling `reward-details.json`. The generated finalizer requires a nonempty
trajectory, successful judge exit, one parsed binary `integrity` criterion,
consistent raw/aggregate decisions, and an actual judge response without an
error. A raw decision may be yes/no or numeric 0/1, matching current RewardKit.

`reward.json` and `reward.txt` contain the metric gated by healthy acceptance.
`judge-status.json` separately records judge health, acceptance, primary/judge
exit statuses and `measurement_valid`. A healthy rejection or measured candidate
failure has zero reward; unavailable/malformed judging or trusted failures
produce a nonzero verifier exit and an invalid measurement. A zero reward alone
does not establish a valid run.

## Derive and verify budgets

Record a budget table in `VALIDATION.md` and summarize it in the README:

1. Enumerate all submission stages, serial/repeated calls, startup, recovery and
   cleanup; assign explicit limits to each candidate phase.
2. Fit their permitted execution paths plus trusted metric overhead inside the
   primary grader supervisor window. Do not confuse candidate build time with
   `[environment].build_timeout_sec`, which covers Docker image construction.
3. Bound the complete judge wrapper, including session retries/initialization;
   its budget is distinct from `judge.timeout` in the rubric.
4. Make `[verifier].timeout_sec` cover the primary and judge supervisors plus
   finalization, termination grace periods and setup/cleanup overhead.

The generated defaults are an initial profile:
`1800 primary + (900 judge session + 300 wrapper overhead) + 600 overhead = 3600`.
`--grader-timeout-sec` and `--judge-timeout-sec` recompute this outer window.
The extra 600 seconds covers finalization (30 seconds), kill grace periods and
setup/cleanup; validate it for the actual workload. A long justified workload
may need a long verifier window. Keep nested limits and the documented task
contract aligned when revising either.

Primary/judge/finalizer stdout and stderr are saved separately, with timestamped
phase boundaries in `stages.log`. Add per-candidate-stage logs and progressive
metrics in the real grader so interruption preserves useful evidence. Test a
fast synthetic timeout to verify cleanup and diagnostics without running the
full time allowance.

## Resource and runtime validation

The helper generates CPU/RAM/swap limits for both Compose phases using the same
values as TOML and visible docs. GPU defaults request one NVIDIA device in both
phases; `--gpu-device` on the common launcher selects the actual device. Verify
the effective container settings. Add task-specific storage, cgroup/RSS and GPU
memory controls where their public constraints require them; metadata is not
evidence of enforcement.

Before delivery, test the real grader with known-good and invalid submissions,
then test healthy audit acceptance/rejection and missing, inconsistent or timed
out audit results. Inspect metrics, rewards, process cleanup and health files.
Finally follow the configured-model feedback loop and record evidence for the
final task/instruction revision in `VALIDATION.md`.
