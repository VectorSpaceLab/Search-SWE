# Quick start

Use Python 3.12+ and a native Linux x86_64 Docker host with enough resources for
the selected tasks. The CLI and its pinned Harbor dependency run on the host;
task-specific libraries run inside Docker.

You can follow the CLI workflow below, or install the
[evaluation skill](agent-evaluations.md) and ask your agent to run your chosen
settings and tasks.

## Install

The PyPI release installation command is `python -m pip install search-swe`.
This development version is not yet published; install it from the checkout:

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
python -m pip install -e .
search-swe doctor
```

Use an isolated Python environment if needed. Task definitions and assets remain
in the checkout; a wheel installation also needs that checkout, selected through
the current directory, `--repo PATH`, or `SEARCH_SWE_REPO`.

## Configure and run

```bash
search-swe run
```

Choose the harness and provider, then search for a model and select its reasoning
level before entering the required API keys. For OpenRouter, type a model name
or ID, use the arrow keys to select a match, and press Enter; a complete model
ID can also be entered manually. The default is Codex + OpenRouter + `openai/gpt-6-luna` with `max`
reasoning. Keys are hidden while typing, and an existing key can be reused
without displaying it.

Select tasks with Space and confirm with Enter. For a first CPU run,
`reasoning-query-rewriting` has a small asset bundle. Choose sequential execution
initially, or select parallel execution and its concurrency limit. The wizard
asks for the selected tasks' judge credentials and optionally their submission
API keys. Review the summary, choose whether to save `.env`, and confirm starting.

The CLI downloads missing assets, validates checksums, assigns CPU/GPU resources,
prepares task-specific storage and launches the existing Harbor integration.
Cancellation before the final confirmation does not modify `.env`.

## Run with saved settings

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

Use `search-swe configure` to configure without launching, `search-swe list` to
list tasks, and `--dry-run` to preview without downloads, API calls or writes.
Non-interactive scripts supply `--yes`. Keys stay in `.env` or process environment
variables, never command-line arguments. Exported values override saved file
values on subsequent invocations.

## Inspect results

The CLI prints the batch directory and each task's log path. Under
`jobs/evaluations/<unique-run>/`, `run.json` records settings, allocations and
result locations; `logs/` contains preparation and evaluation logs. Read Harbor's
reports for the score and judge health: process completion is not a passing score.

See the [CLI reference](cli.md) for resource pools, offline assets and packaging;
the [full evaluation guide](evaluation.md) for credentials and native launcher
options; and [network policy](network-policy.md) for proxy configuration.
