# Search-SWE documentation

New to Search-SWE? Read the [benchmark design](benchmark.md) for the evaluation
model, then follow the [quick start](evaluation/quickstart.md) to run your first
task with the CLI or your coding agent.

## Run evaluations

| Guide | Use it to |
| --- | --- |
| [Quick start](evaluation/quickstart.md) | Install, choose CLI or agent operation, and inspect your first results |
| [CLI reference](evaluation/cli.md) | Configure settings, select tasks, and schedule sequential or parallel batches |
| [Supported agents and providers](evaluation/agents.md) | Discover Harbor agents, choose provider routes, and configure harness versions and authentication |
| [Submission model access](evaluation/submission-models.md) | Apply the required OpenRouter model allowlists to submission API keys |
| [Data and models](evaluation/assets.md) | Plan disk space, download, verify, and restore fixed inputs |
| [Host setup and single-task launcher](evaluation/runtime.md) | Configure credentials, CPU/GPU allocation and task storage, or run a single task directly |
| [Network policy](evaluation/network.md) | Configure runtime allowlists, direct gateway access and proxy egress |

Each task's `README.md`, `instruction.md` and `task.toml` under
[`tasks/`](../tasks/) describe its requirements, submission interface and resource
budget. Start with those files for task-specific setup or scoring questions.

## Contribute and maintain

| Guide | Use it to |
| --- | --- |
| [Task contributions](contributing/tasks.md) | Create a task, evaluate and refine it with a coding model, and prepare its review and assets |
| [Contributor and maintainer skills](../.agents/AGENTS.md) | Follow the detailed task-authoring or PR-review workflow with an agent |
| [Repository tools](../scripts/README.md) and [tests](../tests/README.md) | Find checkout scripts, run regressions and select Docker integration checks |
| [CLI package releases](contributing/cli-release.md) | Build, validate and publish a CLI release to PyPI |

The [benchmark design](benchmark.md) also covers repository structure and data
provenance. For task descriptions and published results, visit the
[project website](https://search-swe.github.io/).
