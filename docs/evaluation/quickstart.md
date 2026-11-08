# Quick start

[Documentation index](../README.md)

Use Python 3.12+, Git and native Linux x86_64 with local rootful Docker. Choose
CPU, RAM, disk and optional GPU capacity to match the tasks; see
[host requirements](runtime.md#prerequisites).

## Install

In your Python environment:

```bash
pip install search-swe
```

The CLI uses a separate Search-SWE checkout for tasks, data and results. On first
interactive use, choose an existing checkout or clone to `~/Search-SWE` or a
custom path. The CLI remembers it. CLI and checkout must use the same release
series, currently 0.3.x.

Use `search-swe info` to inspect that checkout. Between evaluation batches,
`search-swe update --check` previews new tasks and `search-swe update` applies
compatible upstream updates. Ordinary task additions need no CLI release.

## Run with the CLI

```bash
search-swe run
```

1. Choose the harness, provider, model and reasoning level. The default is
   **Codex + OpenRouter + `openai/gpt-6-luna` with `max` reasoning**. OpenRouter
   models support search; see [supported agents and providers](agents.md).
2. Enter missing coding-agent credentials. Select tasks with Space, then Enter.
3. Review download locations and disk requirements, then configure the selected
   tasks' judge credentials and any optional services you want to enable.
4. Choose sequential or parallel execution, review resources, and confirm
   saving settings and starting the run.

**Enabled OpenRouter submission keys require the exact model allowlists:** 47
models for the shared key and 17 for reasoning-query-rewriting. Configure these
in OpenRouter using the [key setup guide](submission-models.md); the CLI checks
them before saving or running. Coding-agent and judge keys have separate access.

The CLI saves approved settings in `.env`, downloads missing assets and launches
the tasks. It reuses saved values and asks only for the new selection's missing
credentials. Use `search-swe configure TASK --edit-credentials` to review keys or
disable optional services. Keep key values in local configuration.

## Run with your agent

### Install the skill

Run either installer in your coordinating agent's workspace. These examples use
Codex; replace `codex` with a supported agent such as `claude-code`.

```bash
npx skills add VectorSpaceLab/Search-SWE --skill run-searchswe-evaluation -a codex
```

Or use a GitHub CLI version that provides `gh skill install`:

```bash
gh skill install VectorSpaceLab/Search-SWE skills/run-searchswe-evaluation --agent codex
```

Reload skills or start a new agent session. The skill uses the installed CLI and
host environment; your coordinating agent can differ from the model evaluated.

### Describe the experiment

> Use run-searchswe-evaluation with /path/to/Search-SWE. Evaluate agentic-search
> and agentic-search-vectorless with Codex, OpenRouter, openai/gpt-6-luna and max
> reasoning. Use the existing .env and run at most two tasks concurrently.
> Monitor progress and report scores, verifier health and result paths.

For preparation only, tell the agent to configure the run and stop before
launching. It will identify missing credentials and ask you to configure them
locally. Each batch uses one model setting.

### Skill installation options

Both installers default to project scope. Use `npx skills add ... -g` or
`gh skill install ... --scope user` for user-wide installation. `npx skills`
requires Node.js 22.20+; check `gh skill install --help` for GitHub CLI support.
See the [installer docs](https://github.com/vercel-labs/skills) and
[GitHub CLI reference](https://cli.github.com/manual/gh_skill_install).

For a local checkout:

```bash
npx skills add /path/to/Search-SWE --skill run-searchswe-evaluation -a codex
gh skill install /path/to/Search-SWE run-searchswe-evaluation --from-local --agent codex
```

GitHub CLI selects the latest release, falling back to the default branch;
`--pin FULL_COMMIT_SHA` selects a revision. With `npx skills`, use a GitHub tree
URL for a branch or tag. Match the skill to your CLI and checkout.

### Update the skill

The skill records its matching CLI release in `SKILL.md` as `metadata.version`
(currently `0.3.0`), with compatible CLI/checkout series `0.3.x`.
For a project installation, run these commands in your coordinating agent's
workspace:

```bash
npx skills check -p
npx skills update run-searchswe-evaluation -p
```

Use `-g` instead of `-p` for a global installation. GitHub skill updates follow
the recorded source's content changes; version metadata records CLI alignment.
Refresh a local-path installation by repeating its original `skills add` command.
Reload skills or start a new agent session after updating. The skill, Python
package and task checkout are updated separately; keep their release series
aligned. See the [Skills update commands](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-update).

## Run with saved settings

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

Use `search-swe configure` for setup only, `search-swe list` for tasks,
`search-swe doctor` for host checks, and `--dry-run` to preview a run.
See the [CLI reference](cli.md) for scripting and configuration precedence.

## Inspect results

The CLI prints the batch directory and task log paths. Under
`jobs/evaluations/<unique-run>/`, `run.json` records settings, allocations and
result locations; `logs/` contains preparation and evaluation logs. Read Harbor's
reports for scores and judge health: process completion alone is not a passing score.
