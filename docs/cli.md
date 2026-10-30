# Search-SWE CLI

Configure coding-agent evaluations interactively, restore fixed inputs, and run
one model setting across selected Search-SWE tasks sequentially or concurrently.
For agent-driven operation, install the [evaluation skill](agent-evaluations.md)
and describe the settings and tasks to your agent.

## Installation

The distribution name and command are both `search-swe`. This checkout contains
the unpublished `0.1.0.dev0` development version. Once published, installation is:

```bash
python -m pip install search-swe
```

For the current local version, install from the repository root:

```bash
python -m pip install -e .
search-swe --help
```

Python 3.12+ is required. Package dependencies are declared in
`pyproject.toml`, including the pinned Harbor version. Use a virtual
environment to isolate these dependencies. The wheel contains the CLI; task
definitions, Docker integration and fixed assets live in a Search-SWE checkout:

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
search-swe run
```

Repository discovery uses `--repo`, then `SEARCH_SWE_REPO`, then the current
directory and its parents. Editable installations also recognize their source
checkout. A wheel installation can run from another directory with
`search-swe --repo /path/to/Search-SWE run`.

## Interactive setup

`search-swe` or `search-swe run` opens the terminal wizard:

1. Choose the harness, then a supported provider. Search/select an OpenRouter
   model, enter a direct-endpoint model ID, or select a supported Pi model.
   Then choose its reasoning or thinking level.
2. Enter the coding-agent API key using hidden input, or retain an existing key.
3. Filter and select tasks with Space, then press Enter. The menu shows their
   CPU, RAM, GPU and asset requirements.
4. Configure the selected tasks' required judge credentials. Optional APIs for
   submitted programs have a separate opt-in prompt.
5. Choose sequential execution or a maximum parallelism, review the setting and
   resource requirements, select an idle GPU pool for GPU tasks, then confirm
   saving and starting.

`search-swe configure` uses the same configuration flow without starting an
evaluation. Model/harness compatibility follows the existing backend: Codex
supports OpenRouter and direct endpoints; Claude Code supports its direct
Anthropic API and Anthropic models through OpenRouter; Pi uses the repository's
DeepSeek/Z.ai direct adapters.

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

Suggestions use the selected harness and available text/tool/API metadata;
Claude Code suggestions are limited to Anthropic models. Metadata filtering
does not replace an actual harness/model compatibility test. The directory may
not expose every supported reasoning level. When selecting a new model, the
wizard starts with **Model/config default**, which omits the explicit effort
override. Models that list no reasoning support use that setting automatically.
Other models offer an explicit level selection; choose a level supported by the
model/provider. The saved model setting is reused on subsequent runs.

`--reasoning-effort default` selects the same behavior in scripted runs. This
uses the model/harness configuration, including any custom Codex configuration;
it does not mean that reasoning is disabled. Catalog selection and configuration
do not start paid model requests.

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

`--task NAME` may also be repeated. Non-interactive runs use `--yes`; missing keys
produce a configuration error instead of waiting for input. `--dry-run` previews
configuration and commands without writing files, downloading assets, allocating
devices or calling model APIs. `--offline` uses local asset caches; evaluation
still requires access to the selected model APIs. Asset restoration verifies
SHA-256 and replaces corrupt manifest-owned files with verified copies.

## Parallel execution and results

`--concurrency N` limits simultaneous tasks. The scheduler allocates disjoint
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
Tasks using bounded filesystems need the host prerequisites described in the
repository evaluation guide. Their storage helpers run with root/sudo while
Harbor retains the invoking user's identity. For unattended runs, arrange
non-interactive sudo access in advance.

## Building for publication

```bash
python -m pip install build
python -m build
```

Inspect both wheel and sdist before publishing. They should contain the CLI,
metadata, license and documentation, with no `.env`, task
datasets, trajectories or job outputs. Publication is a separate maintainer
action; the development package has not been uploaded to PyPI.
