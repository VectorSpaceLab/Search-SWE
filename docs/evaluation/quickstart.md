# Quick start

[Documentation index](../README.md)

Use Python 3.12+, Git and a native Linux x86_64 host with rootful Docker and enough CPU,
RAM, disk space and optional GPU capacity for the selected tasks. The CLI runs
on the host; task-specific libraries run inside Docker.

Install once, then choose [interactive CLI](#run-with-the-cli) or
[agent-assisted operation](#run-with-your-agent). Both use the same runner and
task contracts. See [supported agents and providers](agents.md) for model choices.

## Install

Use an isolated Python environment and a CLI and checkout from the **0.2.x**
series:

```bash
pip install search-swe
```

Task definitions, assets and results live in a separate repository checkout.
When no checkout is found, interactive `run` and `configure` offer to clone to
`~/Search-SWE`, use a custom location, or select an existing checkout. The CLI
remembers that path. Use `--repo PATH` to select another checkout explicitly;
prepare the checkout first for unattended commands.

For local CLI development, use `python -m pip install -e .` from the repository root.

## Run with the CLI

```bash
search-swe run
```

Choose a harness and provider, then a model and reasoning level. For OpenRouter,
search by model name or ID, select a match with the arrow keys and press Enter;
you can also enter a complete model ID. The default setting is **Codex +
OpenRouter + `openai/gpt-6-luna` with `max` reasoning**.
Enter any missing coding-agent credentials. Existing values can be reused;
keys are hidden while typing.

Select tasks with Space and confirm with Enter. For a first CPU run,
`reasoning-query-rewriting` has a small asset bundle. The wizard shows the asset
destination, cache location and estimated disk space. Start with sequential
execution, or choose parallel execution and its concurrency limit.

The wizard asks for the selected tasks' missing judge and service credentials.
For every enabled OpenRouter submission key, apply the required
[model allowlist](submission-models.md): 47 models for the shared key and 17 for
the reasoning-query-rewriting key. The CLI checks these restrictions before
saving or running. Coding-agent and judge keys use their own model permissions.

Review the summary, choose whether to save `.env`, and confirm starting. The CLI
downloads missing assets, validates checksums, assigns resources, prepares task
storage and launches Harbor. Cancellation before final confirmation leaves
`.env` unchanged. See [data and models](assets.md) to relocate the cache or
prepare assets in advance.

## Run with your agent

The `run-searchswe-evaluation` skill guides your coding agent through configuration,
resource selection, execution, monitoring and result inspection. The coordinating
agent can differ from the harness and model being evaluated.

### Install the skill

Run either installer in your coordinating agent's workspace. These examples
target Codex; replace `codex` with your supported agent, such as `claude-code`.

```bash
npx skills add VectorSpaceLab/Search-SWE --skill run-searchswe-evaluation -a codex
```

Or, with a GitHub CLI version that provides `gh skill install`:

```bash
gh skill install VectorSpaceLab/Search-SWE skills/run-searchswe-evaluation --agent codex
```

Reload your agent's skills or start a new session after installation. The skill
uses the separately installed CLI and the host requirements described above.

### Describe the experiment

Tell the agent which checkout and Python environment to use, then describe the run:

> Use run-searchswe-evaluation with the checkout at /path/to/Search-SWE. Evaluate
> agentic-search and agentic-search-vectorless using Codex, OpenRouter,
> openai/gpt-6-luna and max reasoning. Run at most two tasks concurrently, using
> the existing .env. Track progress and report scores, verifier health and result paths.

For configuration only:

> Use run-searchswe-evaluation to prepare code-embedding-finetuning with Codex +
> OpenRouter + openai/gpt-6-luna, GPU 0 and default reasoning. Check configuration
> and show the command; stop before launching the evaluation.

If credentials are missing, the agent identifies the variables and asks you to
enter them through local hidden prompts or your private `.env`. Keep keys out of
chat. Agents supporting explicit skill invocation can use
`$run-searchswe-evaluation`; otherwise ask the agent to load the installed skill.
Each batch uses one model setting; several settings use separate batches with
resources allocated across them.

### Skill installation options

Both installers use project scope by default. Add `-g` to `npx skills`, or
`--scope user` to `gh skill install`, for availability across projects. The current
`npx skills` release requires Node.js 22.20+. Check `gh skill install --help`;
older GitHub CLI versions need an upgrade. See the
[skills installer documentation](https://github.com/vercel-labs/skills) and
[GitHub CLI reference](https://cli.github.com/manual/gh_skill_install).

For a local checkout, use either command:

```bash
npx skills add /path/to/Search-SWE --skill run-searchswe-evaluation -a codex
gh skill install /path/to/Search-SWE run-searchswe-evaluation --from-local --agent codex
```

GitHub CLI resolves unpinned remote installs from the latest release, falling back
to the default branch; `--pin FULL_COMMIT_SHA` selects a published revision.
For `npx skills`, use a GitHub tree URL to select a branch or tag. Match the
[installed skill](../../skills/run-searchswe-evaluation/SKILL.md) to your CLI and checkout.

## Run with saved settings

```bash
search-swe doctor
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

Use `search-swe configure` to configure without launching, `search-swe list` to
list tasks, and `--dry-run` to preview without downloads, API calls or writes.
Non-interactive scripts supply `--yes`. Keys stay in `.env` or process environment
variables; exported values override saved file values on subsequent invocations.
Use `search-swe configure TASK --edit-credentials` to review existing credentials,
including disabling optional services.

## Inspect results

The CLI prints the batch directory and each task's log path. Under
`jobs/evaluations/<unique-run>/`, `run.json` records settings, allocations and
result locations; `logs/` contains preparation and evaluation logs. Read Harbor's
reports for the score and judge health: process completion is not a passing score.

See the [CLI reference](cli.md) for command options, the
[host and native launcher guide](runtime.md) for advanced setup, and
[network policy](network.md) for proxy configuration.
