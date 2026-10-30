---
name: run-searchswe-evaluation
description: Configure, launch, monitor and summarize evaluations of existing Search-SWE tasks using the search-swe CLI. Use when the user specifies models, harnesses, providers, tasks or resource settings for benchmark runs, including preparation-only requests.
license: Apache-2.0
---

# Run Search-SWE evaluations

Translate the user's requested settings and tasks into reproducible CLI batches,
follow their progress, and report scores together with verifier health. This skill
coordinates the host-side runner; the selected harness runs the evaluated coding
agent inside the task environment. Preserve task instructions, resource budgets,
input specifications and verifier contracts while operating the benchmark.

## Locate the runtime

The installed skill is portable; its directory is independent of the benchmark
checkout. Locate the checkout from the user's path, `SEARCH_SWE_REPO`, or the
current workspace. Reuse its existing branch and working tree. If a checkout is
needed, obtain `https://github.com/VectorSpaceLab/Search-SWE` in the user's chosen
workspace. Task definitions and backend scripts come from that checkout.

Use a Python 3.12+ host environment with the Search-SWE package installed. Check
`search-swe --version` and `search-swe run --help`. The current development
checkout installs with `python -m pip install -e /path/to/Search-SWE`; the published
distribution installs with `python -m pip install search-swe`. An installed skill
provides instructions; the package supplies the executable.

Read `docs/cli.md` in the selected checkout for its supported flags. Read
`docs/evaluation.md` only for provider, network or bounded-storage setup details.
These paths are relative to the benchmark checkout, not this installed skill.

## Resolve the requested experiment

- Preserve the requested harness, provider, complete model ID, reasoning/thinking
  level, task names, concurrency and CPU/GPU/RAM pool. Use existing configuration
  for omitted values, and identify material ambiguities before launching.
- Discover names/resources with `search-swe --repo /path/to/Search-SWE list --json`.
  Inspect the selected task READMEs and `task.toml` for runtime and service needs.
- Codex supports OpenRouter or a direct endpoint; Claude Code supports its direct
  Anthropic endpoint and Anthropic models through OpenRouter; Pi uses the
  checkout's supported direct adapters. For an ambiguous OpenRouter name, consult
  `https://openrouter.ai/api/v1/models` or cached catalog metadata described in
  the checkout's CLI guide, and resolve the full ID.
  Directory metadata alone is not proof of harness compatibility.
- Use one model setting per batch and one attempt per selected task by default.
  For a requested model matrix, create separate batches and coordinate resources
  across them. The CLI coordinates allocations within one invocation.
- The repository default is Codex + OpenRouter + `openai/gpt-6-luna`, reasoning
  `max`. For a new model with no specified or matching saved effort, use `--reasoning-effort default`
  to keep its model/harness configuration. This is distinct from disabling reasoning.

A request to run a concrete experiment authorizes that batch. Continue once its
configuration is ready; ask for missing choices, credentials or resource access
that actually block it. For a preparation-only request, finish configuration and
the command preview without launching an evaluation.

## Prepare configuration and resources

For execution, run `search-swe --repo /path/to/Search-SWE doctor --json` and inspect
available host resources. Configuration can be prepared before runtime host
requirements are satisfied; report what remains before an actual launch.
Choose a dedicated pool on shared machines with `--cpu-set`,
`--gpu-devices` and `--memory-gb` when appropriate. `--concurrency` is a maximum;
the CLI queues tasks until their allocations fit. Bounded-storage tasks need
host FUSE and root/sudo; arrange authorization before an unattended launch.

Reuse the ignored checkout `.env`, an explicitly selected `--env-file`, or
exported variables. Explicit CLI options override saved settings; exported
variables override file values. Inspect credential presence through the CLI's
validation errors or boolean checks, keeping values out of chat and tool output.

When a required key is missing, name the variable and its purpose, and ask the
user to configure it locally. Give them `search-swe --repo /path/to/Search-SWE
configure` with the requested task/setting flags so they can use hidden input,
or identify the private env file to edit. Resume after configuration is available.
Keep agent, trajectory-judge, answer-judge and submission-resource credentials in
their declared roles; reuse a key across roles only when the user has selected it.

Use `configure ... --yes` to validate and save specified defaults when the needed
credentials are already available. It makes no model calls. Keep environment files
Git-ignored and mode `0600`; the CLI preserves unrelated settings. Optional task
APIs follow the task's resource documentation and the user's choices.

## Preview and launch

Use explicit flags and `--yes` for agent-driven execution, avoiding a terminal
wizard waiting on an agent tool's stdin. For example, from the selected checkout:

```bash
search-swe run agentic-search agentic-search-vectorless \
  --agent codex --provider openrouter --model openai/gpt-6-luna \
  --reasoning-effort max --concurrency 2 --dry-run
```

After configuration and resources are ready, replace `--dry-run` with `--yes` for
the authorized run. The preview does not validate credentials, assets or API
connectivity. Runtime preflight checks the configuration before data restoration
and startup; it is not a paid model probe. Use the normal runner for evaluation
and retain its asset checks and phase isolation.

The CLI restores verified assets, prepares bounded storage where needed, and
launches the task harness/verifier. `--offline` uses cached assets and model
metadata; evaluation still needs its configured model APIs. Use a fresh `--output`
path or the generated `jobs/evaluations/<unique-run>/` directory. Output paths are
relative to the invoking directory when supplied; use absolute paths for handoffs.

For long experiments, use an available persistent execution session or a detached
process with stdin closed and launcher output redirected to a private log. Record
the session/PID, command without secret values, checkout revision, batch directory
and log path. Verify the process started and the batch summary appeared. Keep any
launcher log outside a custom `--output` directory, which must not exist at startup.

## Monitor and report

Read the batch `run.json` and task log tails at intervals suited to the task's
runtime and the user's preference. Check the recorded task output directories for
Harbor results, rewards, verifier errors and judge health. Asset restoration may
take time before any task enters its agent phase.

`completed` in `run.json` means the launcher exited successfully; it is not a
passing score. Distinguish an observed task score from setup/authentication,
infrastructure or verifier failures. A running process or command preview is not
a completed evaluation. Report task, model/harness/provider/effort, status, score
when available, judge/verifier health and paths to evidence.

On interruption, signal the recorded CLI process with SIGINT or SIGTERM and allow
its teardown to finish. If storage remains attached, follow that run's printed
recovery instructions after its containers exit. Keep completed results and
unrelated workloads intact. Diagnose a failed attempt before proposing a targeted
rerun, respecting the user's retry and spending limits; a low score is a result.
For an ongoing background run, report its actual state and monitoring handles.
