# Run evaluations with your agent

Install `run-searchswe-evaluation` into your coding agent, then describe the model
settings and tasks you want to evaluate. The skill guides configuration, resource
selection, CLI execution, monitoring and result inspection. Both this workflow
and the [interactive CLI](quickstart.md) use the same runner and task contracts.

## Install the skill

Run an installer from the workspace used by your coordinating agent. These
examples target Codex; replace `codex` with your supported agent, such as
`claude-code`. Install using either tool.

With the skills installer:

```bash
npx skills add VectorSpaceLab/Search-SWE --skill run-searchswe-evaluation -a codex
```

Or, with a GitHub CLI version that provides `gh skill install`:

```bash
gh skill install VectorSpaceLab/Search-SWE skills/run-searchswe-evaluation --agent codex
```

Both examples install at project scope. Use `-g` with `npx skills`, or
`--scope user` with `gh skill install`, for availability across projects. Check
`gh skill install --help` when choosing the GitHub CLI route; older `gh` versions
need an upgrade. The current `npx skills` release requires Node.js 22.20+.
See the [skills installer documentation](https://github.com/vercel-labs/skills)
and [GitHub CLI installation reference](https://cli.github.com/manual/gh_skill_install).

To install from a local checkout, use its path:

```bash
npx skills add /path/to/Search-SWE --skill run-searchswe-evaluation -a codex
```

Or:

```bash
gh skill install /path/to/Search-SWE run-searchswe-evaluation --from-local --agent codex
```

GitHub CLI resolves an unpinned remote install from the latest release, falling
back to the default branch. Use `--pin FULL_COMMIT_SHA` to select a particular
published revision. For `npx skills`, a GitHub tree URL can select a published
branch or tag. Match the installed skill to the checkout/CLI you intend to use.
Reload your agent's skills or start a new session after installation.

## Prepare the evaluation host

The agent still needs a Search-SWE checkout, the CLI, Python 3.12+ and a native
Linux x86_64 Docker host with the selected tasks' resources. Install the CLI with
`python -m pip install search-swe`. For local CLI development, use
`python -m pip install -e /path/to/Search-SWE`. The skill itself is an instruction
package and uses the separately installed CLI.

Interactive `search-swe configure` can clone to `~/Search-SWE`, accept a custom
clone path, or select an existing checkout, and remembers the chosen path. For
unattended commands, prepare the checkout first and pass `--repo PATH`.

Tell the agent which checkout and environment to use. It will inspect the task
catalog and host, resolve your setting, and prepare a non-interactive command.
If keys are missing, it identifies the required variables and asks you to enter
them through local hidden prompts or your private `.env`. Keep keys out of chat.
Existing environment credentials can be reused without displaying their values.

## Describe the experiment

For example:

> Use run-searchswe-evaluation with the checkout at /path/to/Search-SWE. Evaluate
> agentic-search and agentic-search-vectorless using Codex, OpenRouter,
> openai/gpt-6-luna and max reasoning. Run at most two tasks concurrently, using
> the existing .env. Track progress and report scores, verifier health and result paths.

For configuration only:

> Use run-searchswe-evaluation to prepare a run of code-embedding-finetuning with
> Codex + OpenRouter + openai/gpt-6-luna, using GPU 0 and default reasoning.
> Check configuration and show the command; stop before launching the evaluation.

Agents supporting explicit `$skill-name` invocation can use
`$run-searchswe-evaluation`. Otherwise ask the agent to load that installed skill.
The coordinating agent may differ from the harness/model being evaluated.

Each CLI batch runs one model setting over one or more tasks. For several model
settings, the agent prepares separate batches and allocates resources across
them. Results and logs use `jobs/evaluations/<unique-run>/` by default. The agent
reads actual Harbor scores and verifier health alongside the CLI process status.

See the [skill source](../skills/run-searchswe-evaluation/SKILL.md) and
[CLI reference](cli.md) for the complete workflow and command options.
