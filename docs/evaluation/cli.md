# Search-SWE CLI

[Documentation index](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/README.md)

Configure coding-agent evaluations interactively, restore fixed inputs, and run
one model setting across selected Search-SWE tasks sequentially or concurrently.
For agent-driven operation, install the [evaluation skill](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/quickstart.md#run-with-your-agent)
and describe the settings and tasks to your agent.

## Installation

This guide describes CLI **0.2.x** and a **0.2.x Search-SWE checkout**. Patch
versions within that series are compatible. The distribution and command are
both `search-swe`. Install from PyPI:

```bash
python -m pip install --upgrade 'search-swe>=0.2,<0.3'
```

For local CLI development, install from the repository root:

```bash
python -m pip install -e .
search-swe --help
```

Python 3.12+ is required. Package dependencies are declared in
`pyproject.toml`, including the pinned Harbor version. Use a virtual
environment to isolate these dependencies. The wheel contains the CLI; task
definitions, Docker integration and fixed assets live in a Search-SWE checkout.
Start the wizard to choose or prepare that checkout:

```bash
search-swe run
```

When no checkout is found, interactive `run` and `configure` offer three choices:
clone to `~/Search-SWE`, clone to a custom path, or select an existing checkout.
Git is required for cloning. Accept the clone destination to download the
repository's latest `main` snapshot with a shallow clone, then continue with model configuration. A valid
checkout at the chosen path is reused; cloning uses a new or empty directory.

The selected path is saved in `$XDG_CONFIG_HOME/search-swe/repository.json`
(default `~/.config/search-swe/repository.json`) and reused by future commands.
Repository setup completes before model configuration; task assets and results
belong to the selected checkout, while the CLI stays in the Python environment.

Repository discovery uses `--repo`, then `SEARCH_SWE_REPO`, then the current
directory and its parents. Editable installations also recognize their source
checkout, followed by the remembered path. To override discovery, use
`search-swe --repo /path/to/Search-SWE run`. Scripted commands (`--yes`), dry runs,
`list` and `doctor` require an existing checkout. With `--offline`, the interactive
selector offers existing checkouts only.

Before configuration, the CLI checks the checkout's declared version. Update
the Python package and checkout together, or select a compatible checkout with
`--repo`. The CLI leaves checkout updates and local changes under your control.

## Interactive setup

`search-swe` or `search-swe run` opens the terminal wizard:

1. Choose the harness, then a supported provider. Search/select an OpenRouter
   model, enter a direct-endpoint model ID, or select a supported Pi model.
   Then choose its reasoning or thinking level.
2. Enter any missing coding-agent credentials using hidden input. Existing values
   are reused.
3. Filter and select tasks with Space, then press Enter. The menu shows their
   CPU, RAM, GPU and asset requirements. Review the asset/cache paths and disk
   space estimate before configuring task services.
4. Fill missing required service credentials for the selected tasks. Choose any
   optional submission APIs to enable from a separate checklist. Task-specific
   setup instructions identify model restrictions and credential roles.
5. Choose sequential execution or a maximum parallelism, review the setting and
   resource requirements, select an idle GPU pool for GPU tasks, then confirm
   saving and starting.

`search-swe configure` saves the model setting, API keys and default concurrency.
Task selection is optional and determines which service credentials to configure.
Choose tasks for each evaluation with `run`; its resource pool and output options
apply to that invocation. Use `search-swe configure --help` for configuration
options and `search-swe run --help` for execution options.

Codex, Claude Code and Pi support OpenRouter. Direct routes use Codex-compatible
endpoints, the official Anthropic API, or Pi's bundled API-key providers.
See the [supported agent matrix](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/agents.md)
for model and authentication scope. `search-swe pi-models` lists Pi providers;
add `--provider NAME` to see their exact model IDs.

The default is Codex + OpenRouter + `openai/gpt-6-luna`, with `max` reasoning.
Custom models must support the selected harness/API; choosing a model does not
perform a paid connectivity test. Existing task-specific verifier models and
network allowlists continue to apply.

### OpenRouter model search

The model field searches the public OpenRouter directory by name and model ID
as you type, including multiple keywords. Use ↓/↑ to highlight a result and
Enter to select its full ID; matching rows show the name and context length.
Enter on an empty field keeps the displayed current/default model. A complete
model ID can also be typed manually for newly available or custom models.

The directory is fetched once and searched locally; typing does not issue API
requests. Metadata is cached for 24 hours under
`$XDG_CACHE_HOME/search-swe/openrouter-models.json` (default
`~/.cache/search-swe/openrouter-models.json`). Use `search-swe run --refresh-models`
to refresh it, or `--offline` to use the cache without a catalog request. If the
directory is unavailable, cached results or manual model input remain usable.
Catalog requests use the public endpoint and carry no API keys.
Pi models absent from its bundled directory require compatible live or cached
metadata. Configure/run resolves it before asking for credentials or preparing
assets; `--offline` uses cached metadata, and the adapter uses the resolved copy.

Suggestions use the selected harness and available text/tool/API metadata:
Responses for Codex, Messages for Claude Code, and Chat Completions for Pi. Metadata filtering
does not replace an actual harness/model compatibility test. The directory may
not expose every supported reasoning level. When selecting a new model, the
wizard starts with **Model/config default**, which omits the explicit effort
override. Models that list no reasoning support use that setting automatically.
Other models offer an explicit level selection; choose a level supported by the
model/provider. The saved model setting is reused on subsequent runs.

Scripted runs also use `default` when changing the model, harness or provider;
an unchanged setting retains its saved effort. Use `--reasoning-effort LEVEL`
to choose explicitly. `--reasoning-effort default`
uses the model/harness configuration, including any custom Codex configuration;
it does not mean that reasoning is disabled. Selecting the coding-agent model
does not send inference requests. Configuring enabled submission keys includes
the mandatory permission probes described below.

## Credentials and configuration

Configuration is read from the checkout `.env`, or `--env-file PATH`. Command-line
and explicit wizard answers take priority over exported variables, then file
values, then defaults. A saved configuration does not override exported shell
variables in a later invocation; the wizard identifies conflicting variable names.

Keys are hidden during entry and summaries contain no key values. Saving uses an
atomic replacement with mode `0600`, preserves unrelated dotenv settings/comments,
and treats values literally. Saved environment files inside the checkout must be
Git-ignored. Cancelling before the final confirmation leaves the
file unchanged. Choose not to save to use entered values only for this run.

`SEARCH_SWE_AGENT`, `SEARCH_SWE_PROVIDER`, `AGENT_MODEL`,
`AGENT_REASONING_EFFORT` / `PI_THINKING`, and `SEARCH_SWE_CONCURRENCY` hold the
selected defaults. Keys retain their existing purpose-specific variable names.
Reusing the OpenRouter agent key for the trajectory judge requires an explicit
choice; submitted programs receive only their task-declared credentials.

Only the selected tasks determine which service variables are requested. Shared
variables are requested once per batch; fixed model names and endpoints in
`task.toml` are kept as defined. Later runs reuse saved values and ask for the
new selection's missing variables. Use `search-swe configure TASK --edit-credentials`
to review or replace existing values. Select a configured optional service and
choose **Disable / clear** to clear its key for this run and, when saved, in the
environment file. Required services retain their key requirement. An exported
shell value still takes precedence on future runs; unset it there as well when
disabling that service permanently. Other saved variables remain in the file.

Submission services can be optional or required by a task. For example,
`reasoning-query-rewriting` offers its own OpenRouter submission key;
`icsi-meeting-memory` requires its
answerer key at startup. The CLI reads task-owned `metadata.configuration`
guidance alongside the environment mappings. It shows each service's task and
purpose, plus links to the local resource policy. Configure provider-side
restrictions in the OpenRouter dashboard before entering a submission key.

**OpenRouter submission-key allowlists are mandatory:** the shared key uses **47
models** and the reasoning-query-rewriting key uses **17**. They provide a few
lightweight generation models plus embedding and rerank models;
`qwen/qwen3-reranker-8b` is excluded for cost. Coding-agent and judge credentials
have separate model access. The wizard shows a short profile reminder, with
full lists available on demand:

```bash
search-swe submission-models
search-swe submission-models --profile reasoning-query-rewriting
search-swe submission-models --profile shared --json
```

These commands work offline without a checkout or API key. `--json` outputs an
`allowed_models` object for guardrail setup. Follow the
[submission-key setup guide](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/submission-models.md)
to assign it to the corresponding key in OpenRouter. Each task's resource policy
defines permitted uses within that key's available models.

Before saving configuration or starting a batch, the CLI checks each enabled
submission key with three out-of-list requests (`max_tokens=1`). An accepted
request or an inconclusive result blocks the operation with a configuration
error. Probes use a fresh catalog and random candidates; the rewriting profile
also checks its stricter boundary. Existing keys, `--yes` and `--offline` follow
the same rule. Accepted probes may incur small API charges. `--dry-run` makes no
requests. The setup guide explains the checks and their sampled scope.

Previews show required/optional variable names and configured/missing status,
with task-specific guidance and no values. Scripted `--yes` runs with missing
required variables stop with a `configure` command for that exact selection.

## Scripted runs

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless \
  --agent codex --provider openrouter --model openai/gpt-6-luna \
  --reasoning-effort max --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
search-swe run reasoning-query-rewriting --dry-run
search-swe list --hardware cpu
search-swe list --json
search-swe doctor
```

`doctor` reads the same checkout `.env` as `run`; use `--env-file PATH` with either
command to select another environment file. It checks Docker and the local host;
the run preflight also checks the selected tasks' resource and credential needs.

`--task NAME` may also be repeated. Non-interactive runs use `--yes`; missing keys
produce a configuration error instead of waiting for input. `--dry-run` previews
configuration and commands without writing files, downloading assets, allocating
devices or calling model APIs. `--offline` uses local asset caches; submission-key
checks and evaluation still require network access. Asset restoration verifies
SHA-256 and replaces corrupt manifest-owned files with verified copies.

## Parallel execution and results

Task inputs live under `<checkout>/tasks/<task-name>/data` and `models`, as
declared in each manifest. Hugging Face keeps an additional cache, normally
`~/.cache/huggingface/hub`; set `HF_HUB_CACHE` in the shell or selected `.env` to
place it on another disk. `HF_HOME` and `XDG_CACHE_HOME` also affect the default.
The CLI shows both locations, expected additional bytes and filesystem free
space before confirmation or downloads, summing their requirements when they
share a filesystem. `run --dry-run` previews this estimate without API requests.

Estimates use file sizes and cached-source presence. Restoration verifies
SHA-256, reuses valid shared cache entries, and refetches corrupt entries when
online. Allow extra space for checksum repairs, Docker images/builds, task
scratch files and results. The [asset guide](https://github.com/VectorSpaceLab/Search-SWE/blob/main/docs/evaluation/assets.md)
describes native download and cache controls.

`--concurrency N` limits simultaneous tasks. The saved concurrency is reused in
scripted runs and offered as the wizard's default; a fresh configuration uses 1.
The scheduler allocates disjoint
logical CPU sets and one idle physical GPU per GPU task, and admits tasks only
within the RAM pool. It preserves each task's CPU quota, memory cap, storage and
scoring rules. Fixed task CPU-set environment variables remain respected.
Use `--cpu-set 0-31`, `--gpu-devices 0,1`, and `--memory-gb 64` to bound the pool.
RAM accounting leaves 2 GiB for the host and 512 MiB per running task for trusted
infrastructure. GPUs with more than 512 MiB used or over 5% utilization are
considered busy at startup.
GPU availability is checked again while scheduling, so a GPU taken by another
process during asset preparation stays out of the next allocation.

Allocations coordinate this CLI invocation. They do not reserve the machine
against other users or independent launchers; select a dedicated resource pool
on shared hosts. CPU placement can affect timing, so retain allocations when
reproducing performance measurements.

Runs use fresh `jobs/evaluations/<unique-run>/` directories, or a new `--output`
directory. `run.json` records the model setting, checkout revision/dirty state,
per-task resource allocation, process status, log and result paths. A `completed`
status means the launcher exited successfully; inspect Harbor results for task
scores and verifier health. Asset logs and evaluation logs are under `logs/`.

Ctrl-C / SIGTERM stops launching new tasks, forwards cancellation to running
launchers and allows teardown before releasing managed storage. Retained Docker
containers prevent storage unmounting and produce a recovery instruction.
If storage cleanup fails, the batch stops, cancels other active runs and records
`cleanup-error` for the affected task. Queued tasks remain `not-started`; inspect
the retained storage and recovery instructions before starting another batch.
Tasks using bounded filesystems need the host prerequisites described in the
repository evaluation guide. Their storage helpers run with root/sudo while
Harbor retains the invoking user's identity. For unattended runs, arrange
non-interactive sudo access in advance.
