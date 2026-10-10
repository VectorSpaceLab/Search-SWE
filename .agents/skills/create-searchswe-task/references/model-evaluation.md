# Validate the setting with a configured coding model

A real coding-model trial checks whether an agent can understand and execute
the task in its intended environment. It complements known-good and negative
grader tests; neither a strong model's success nor its failure alone proves
benchmark quality. Run the final rewritten `instruction.md`, not the structured
source. Read [validation.md](validation.md) for prerequisites and grader checks.

## Configure and probe

Record the checkout/revision, task and instruction hashes, harness/version,
provider, full model ID, reasoning effort, judge configuration, hardware,
resource limits and intended output directory. Use the user-selected model.
Resolve "maximum reasoning" against the actual harness/provider support; do
not assume `max` and `xhigh` are interchangeable. Verify the effective setting
in the generated config and trajectory. Never substitute a different model
silently.

Inspect `scripts/run_task.py`, the selected task's `task.toml`, and the current
evaluation documentation. Agent credentials, submission API resources,
trajectory judge and any answer judge are separate configuration groups.
Reuse session-authorized keys from an ignored `.env` without printing them or
passing literal secrets in command arguments. Do not alter a shared `.env`
just to run one revised task: use an ignored run-specific env file or process
overrides. Restrict it to its owner and remove temporary secret copies afterward.

Check only whether required variables are configured; never display their
values. Determine the required groups from the selected agent/provider, task
and judges, using the target checkout's `.env.example`, `docs/evaluation.md`
and task configuration. Optional task APIs need keys only when used. If keys
are missing, explicitly remind the contributor to configure them and provide:

- The exact missing variable names and the model, task API or judge each serves.
- The local configuration location: the checkout's ignored `.env`, a supported
  run-specific env file, or process environment. Give placeholders only; preserve
  an existing `.env` instead of overwriting it with the template.
- A request to confirm when local configuration is ready, without sharing key
  values in chat, a PR or logs.

Wait for configuration before the dependent probe/trial, then recheck presence
and authentication without exposing secrets. Continue independent package and
grader checks while waiting. Missing credentials are an unmet prerequisite,
not model failure or permission to skip required validation.

When changing a judge provider/model, first exercise the actual pinned judge
backend on a small fixture or an archived trajectory in a disposable verifier.
Check authentication, full model ID, Responses/tool support, structured result,
exit status and logs. A successful models-list request is insufficient. Keep
judge credentials outside candidate processes, and align the verifier allowlist
with the selected endpoint. Current DeepSeek trajectory judges use
`deepseek/deepseek-v4.1-flash` at `https://openrouter.ai/api/v1`, through RewardKit
0.2.0 and its isolated Codex home. Configure that temporary home, not only the
host Codex settings. The answer-equivalence judge, if present, remains separate.

## Launch and observe

Use `--task <task-name>` to select the task from `tasks/`. Preview
first, then run in a new output directory once inputs, credentials, hardware
and scoped API/GPU authorization are available. An explicit model-evaluation
request supplies authorization for that evaluation; do not ask for it again.
For example, replacing placeholders with the actual agreed task and effort:

```bash
task_name=example-search  # Use the task being evaluated.
bash scripts/run_task.sh --task "$task_name" --agent codex \
  --openrouter --model "$model_id" --reasoning-effort "$effort" --dry-run
bash scripts/run_task.sh --task "$task_name" --agent codex \
  --openrouter --model "$model_id" --reasoning-effort "$effort" \
  --output "$fresh_output"
```

For a separate evaluation checkout, sync only the selected task and necessary
runtime integration files, preserve restored assets and existing results, and
record hashes proving the launched prompt is the reviewed rewrite. Do not give
the evaluated agent reference solutions, hidden tests or previous trajectories.

Use Herdr when requested, following its skill. Read pane/process state and
Harbor results together: a pane can show a monitor after the evaluation ends.
Keep a concurrency cap appropriate to API and hardware limits; start with one
validation trial, and ordinarily no more than two while validating a new setup.
A 429 calls for lower concurrency/backoff, not a wider launch wave. Honor any
user-specified attempt cap; otherwise allow at most three infrastructure attempts
per unchanged validation revision and stop after its first valid completed trial.
Do not retry a valid low score. Revisions below remain subject to the overall
authorized trial/cost budget; a task edit does not reset a user-specified cap.

Poll the specific live process/container and logs. Long indexing, training or
verification can produce little output. An unchanged result file or observer
timeout is not evidence that the worker died. Recheck that worker; do not start
a replacement while it is live. Retry only after a terminal infrastructure
failure and a relevant correction or bounded backoff. A changed task/prompt is
a new validation revision, not an invisible retry of the old experiment.

## Decide what the result establishes

Check all of the following, not just a directory name or reward:

- The job `result.json` has `finished_at`, a positive `n_total_trials`, all
  trials completed, and zero errored/running/pending trials.
- Trial logs, agent exit, artifact collection and the separate verifier agree
  with that terminal state. The transcript actually uses the selected model,
  effort and reviewed instruction.
- Required judges ultimately returned valid, parseable decisions, with no
  unresolved authentication, transport, rate-limit, parse or answer-judging
  errors. Record recovered internal retries separately from full trial attempts.
  Inspect the attempt logs to identify the actual cause: stream reconnection
  events can cause RewardKit to retry a Codex judge even if that process later
  emits an answer. A later valid decision is usable; a fallback zero after
  exhausted retries is not evidence of model weakness. A fail-closed zero can
  still mean an invalid measurement even when Harbor reports no trial error.
- Inspect raw metrics, resource/latency gates, output validity and the trajectory
  audit separately. An integrity rejection, timeout, bad output and low retrieval
  quality are different findings. Compare visible self-tests with hidden scores
  without exposing hidden answers to a future agent.
- Read the trajectory to distinguish implementation difficulty from contradictory
  instructions, missing resources, accidental leakage and verifier defects.
  Repair setting defects and validate the repaired revision. Preserve a valid
  low score as evidence; do not engineer failures to claim model weakness.

`complete` means the run is usable, not that the model earned full credit.
Report the exact observed score and limitations of this sample. Cost fields
that are null are unknown, not zero; token-based estimates and provider billing
must be distinguished, including judge and failed-attempt costs when available.

## Use feedback to refine the setting

For each valid trial, record what the trajectory and evaluation reveal about
the task. Distinguish solver mistakes from task-setting defects such as an
ambiguous interface, unavailable inputs, contradictory resource limits or an
incorrect verifier. Use concrete evidence to revise the affected instructions,
environment, budgets or grader. Keep `raw-instruction.md`, `instruction.md`,
resource docs and scoring consistent with the revised contract.

Preserve the intended engineering objective and held-out evaluation. Do not
lower thresholds just to turn a valid low score into a pass, tailor the task
to one model's solution, or expose hidden answers in the prompt. If the run
supports the current setting, record why no change is needed.

After a substantive revision, rerun affected package/grader checks and then
the configured model whenever its task or scoring changed. Use a fresh output
directory and record the revised hashes, observations and rationale so evidence
is tied to the final setting. Cosmetic edits or moving completed results do
not require another model run. Stop when the setting is supported by the
checks and a valid interpreted trial, or the agreed budget or a prerequisite
blocks further validation. In the latter case, identify the untested changes
and missing evidence; do not present an earlier trial as validation of them.

## Archive and hand off

Read the destination's `AGENTS.md` before interpreting or moving results. Move
only terminal runs. Under `jobs/evaluations`, follow its task/harness/full-model/
effort/attempt convention, update embedded job and trial paths after a move,
and retain prior valid results. An existing archived completed run should not
be mistaken for a missing run. Stop monitors/queues created for the validation
once they have no work; do not stop unrelated user processes.

Hand off the exact command (without secrets), revision/hashes, run and trajectory
paths, completion and judge status, scores/gate outcomes, resource observations,
cost availability, attempt count and any task changes motivated by the run
(or why none were needed), with validation evidence for the final setting.
Keep unperformed or invalid layers explicit. Do not claim the task validated
until the required model run and its interpretation are supported by evidence.
