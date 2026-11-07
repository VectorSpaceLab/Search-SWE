# Search-SWE CLI

[Documentation index](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/README.md)

Configure evaluations interactively and run one model setting across selected
tasks, sequentially or concurrently. For agent-assisted operation, install the
[evaluation skill](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/quickstart.md#run-with-your-agent).

## Installation

Use Python 3.12+ and a Linux host meeting the
[Docker and hardware requirements](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/runtime.md#prerequisites):

```bash
pip install search-swe
search-swe run
```

The Python package supplies the CLI; a separate checkout holds tasks, backend
scripts, assets and results. CLI and checkout must share a release series,
currently **0.3.x**. Patch versions within that series are compatible. For local
CLI development, install from the checkout with `pip install -e .`.

On first interactive use, choose an existing checkout, clone to `~/Search-SWE`,
or enter a custom location. Cloning needs Git and a new or empty directory;
it fetches a shallow snapshot of `main`. The CLI remembers the selected path
in `$XDG_CONFIG_HOME/search-swe/repository.json` (default
`~/.config/search-swe/repository.json`).

Checkout lookup uses `--repo`, `SEARCH_SWE_REPO`, the current directory and its
parents, an editable installation's checkout, then the remembered path.
Use `search-swe --repo /path/to/Search-SWE run` to select one explicitly.
`--yes`, dry runs, `list` and `doctor` need an existing checkout; `--offline`
offers existing checkouts only. Update the package and checkout together when
changing release series, preserving local work.

## Update tasks and inspect the checkout

Inspect the selected checkout and update it between batches:

```bash
search-swe info
search-swe update --check
search-swe update
```

`info` shows the CLI/checkout versions, path, task count, compatibility and local
Git state. `update --check` fetches the current branch's configured upstream
(normally `origin/main`) and reports commits and added/removed tasks, leaving
checkout files unchanged. `update` applies a compatible fast-forward. Use
`--repo PATH` to select a checkout; both commands support `--json` for agents.

Update between evaluation batches with a clean working tree. Local changes,
unfinished Git operations, detached HEAD and diverged histories produce an
actionable error. Ignored credentials, downloaded assets and job outputs are
preserved; an upstream file that would overwrite them blocks the update.

New tasks are discovered from the checkout and normally need no CLI upgrade.
The target checkout must match the installed CLI's release series. `update`
updates repository files; package upgrades remain separate Python installations.

## Interactive setup

`search-swe` or `search-swe run` opens the wizard:

1. Select the harness, provider, model and reasoning level.
2. Enter missing coding-agent credentials using hidden input.
3. Filter tasks, select with Space and confirm with Enter. Review their resource
   requirements, download locations and disk-space estimate.
4. Configure the selected tasks' required services and choose optional APIs to
   enable. Shared variables are requested once.
5. Choose sequential or parallel execution, select an idle GPU pool if needed,
   and confirm saving settings and starting.

`search-swe configure` saves model settings, credentials and default concurrency
without launching tasks. Its optional task selection determines which service
keys to configure; `run` selects the tasks to evaluate. Use each command's
`--help` for its flags.

The default is **Codex + OpenRouter + `openai/gpt-6-luna`, `max` reasoning**.
Codex, Claude Code and Pi provide integrated OpenRouter routes. All registered
Harbor agents are available through `--provider native`; use `search-swe agents`
to discover them. See the
[agent/provider matrix](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/agents.md)
for direct routes, model scope and [harness versions/cache](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/agents.md#harness-versions-and-installation). `search-swe pi-models` lists Pi providers;
add `--provider NAME` for exact model IDs.

### OpenRouter model search

Search by name or model ID, highlight with ↓/↑ and select with Enter. An empty
field keeps the displayed model; full IDs can also be entered manually.
Suggestions use text, tool and API metadata: Responses for Codex, Messages for
Claude Code, and Chat Completions for Pi. Model selection makes no inference
request; actual compatibility depends on the model/provider.

The public catalog is cached for 24 hours at
`$XDG_CACHE_HOME/search-swe/openrouter-models.json` (default
`~/.cache/search-swe/openrouter-models.json`). Search runs locally. Use
`--refresh-models` to refresh or `--offline` to use cached metadata. Catalog
failure permits cached results or manual input; new Pi OpenRouter models need
compatible live or cached metadata, resolved before credential entry or downloads.

Changing the model, harness or provider defaults reasoning to **Model/config
default**; an unchanged setting keeps its saved effort. Use
`--reasoning-effort LEVEL` to override it. `default` retains the model/harness
configuration, including a custom Codex TOML, rather than disabling reasoning.
Choose explicit levels supported by your model/provider.

## Credentials and configuration

Settings come from the checkout `.env` or `--env-file PATH`, in this order:
explicit flags/wizard answers, exported shell variables, file values, defaults.
The wizard identifies exported variables that override saved values.

Keys are hidden during entry and omitted from summaries. Saving preserves
unrelated settings/comments and writes the file atomically with mode `0600`;
files inside the checkout must be Git-ignored. Values are literal. Cancelling
before final confirmation leaves the file unchanged; declining to save uses
entered values only for that run.

| Saved setting | Variable |
| --- | --- |
| Harness and provider | `SEARCH_SWE_AGENT`, `SEARCH_SWE_PROVIDER` |
| Harness version override | `SEARCH_SWE_AGENT_VERSION` |
| Native agent configuration | `SEARCH_SWE_AGENT_CONFIG` |
| Model and reasoning | `AGENT_MODEL`, `AGENT_REASONING_EFFORT` / `PI_THINKING` |
| Default parallelism | `SEARCH_SWE_CONCURRENCY` |

Only selected tasks determine which service credentials are requested. Later
runs reuse saved keys and ask for missing ones. Task-defined model names,
endpoints and required services remain fixed. Coding-agent, judge and submission
keys have separate roles; reusing the agent key for the trajectory judge requires
an explicit choice.

Use `search-swe configure TASK --edit-credentials` to review or replace keys.
For an optional service, **Disable / clear** clears its key for the run and,
if saved, in `.env`. Required services still need credentials. Unset any exported
shell value too if you want the service to stay disabled on future runs.

**Every enabled OpenRouter submission key needs its exact allowlist:** the shared
key has **47 models**, and reasoning-query-rewriting has **17**. Both exclude
`qwen/qwen3-reranker-8b` for cost. Apply the
[submission-key setup](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/submission-models.md)
in OpenRouter; coding-agent and judge keys have separate access. View/export
profiles offline without credentials:

```bash
search-swe submission-models
search-swe submission-models --profile reasoning-query-rewriting --json
```

Before saving or running, the CLI probes each enabled submission key with three
out-of-list requests (`max_tokens=1`). Accepted or inconclusive responses block
the operation; accepted probes may incur small charges. This also applies to
saved keys, `--yes` and `--offline`. `--dry-run` sends no requests. The setup guide
explains the sampled checks and exact profile requirements.

## Scripted runs

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless \
  --agent codex --provider openrouter --model openai/gpt-6-luna \
  --reasoning-effort max --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

| Command or flag | Behavior |
| --- | --- |
| `list --hardware cpu` / `list --json` | Show task names and resource requirements |
| `doctor` | Check the host and Docker using the checkout `.env` or `--env-file` |
| `--yes` | Use arguments/saved settings; missing required variables produce a configuration error |
| `--dry-run` | Preview settings, disk estimates and commands without prompts, writes, downloads, allocation or API calls |
| `--offline` | Use cached assets/model metadata; harness setup, submission-key checks and evaluation may still need network |
| `--agent-version VERSION` | Use an exact harness version; `default` selects the checkout registry default |
| `--agent-config PATH` | Native agent JSON; relative paths resolve from the selected checkout |
| `--task NAME` | Repeat to select tasks instead of positional names |

## Parallel execution and results

Task copies live under `<checkout>/tasks/<task-name>/data` and `models`;
Hugging Face also keeps a cache, normally `~/.cache/huggingface/hub`.
Set `HF_HUB_CACHE` in the shell or selected `.env` to relocate it. Before
starting, the CLI shows both locations and estimated additional space, combines
requirements on the same filesystem and checks free capacity. Allow extra
space for checksum repairs, Docker images, scratch files and results. See the
[asset guide](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/assets.md)
for cache, repair and standalone download options.

`--concurrency N` limits simultaneous tasks; its default is the saved value or
1. The scheduler assigns disjoint logical CPUs and one idle physical GPU per
GPU task within the RAM pool, preserving task limits and fixed CPU sets.
Use `--cpu-set 0-31`, `--gpu-devices 0,1` and `--memory-gb 64` to bound that pool.
It reserves 2 GiB for the host plus 512 MiB per running task. GPUs above 512 MiB
used memory or 5% utilization are treated as busy and checked again at allocation.
Coordinate with other host users; allocations only cover this CLI invocation.
Keep the same CPU placement when reproducing timing measurements.

Each batch creates `jobs/evaluations/<unique-run>/` or a new `--output` directory:

| Output | Contents |
| --- | --- |
| `run.json` | Setting, checkout revision/dirty state, per-task allocation, status and result paths |
| `logs/` | Asset preparation and evaluation logs |
| Harbor result paths recorded in `run.json` | Scores, verifier health, trajectories and artifacts |

`completed` means the launcher exited successfully; check Harbor reports for
scores and verifier health. Ctrl-C/SIGTERM cancels active runs and lets storage
teardown finish. Cleanup failure stops the batch, cancels other active runs,
records `cleanup-error` and leaves queued tasks `not-started`; follow the recovery
instructions before another batch. Tasks with
[bounded storage](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/runtime.md#bounded-task-storage)
need root/sudo for their storage helper; unattended runs need non-interactive
sudo access. Harbor runs as the invoking user.
