<p align="center">
  <img src="assets/hero.png" alt="Search-SWE — Benchmarking coding agents on building search engines">
</p>

<h1 align="center">
  Search-SWE
  <br>
  <sub>🔍 Benchmarking coding agents on building search engines. 🤖</sub>
</h1>

<p align="center">
  <a href="https://search-swe.github.io/"><img src="https://img.shields.io/badge/Homepage-Search--SWE-0E9B9B?style=for-the-badge&logo=githubpages&logoColor=white" alt="Search-SWE homepage"></a>
  <a href="https://search-swe.github.io/tasks.html"><img src="https://img.shields.io/badge/Task_Gallery-Browse-5865F2?style=for-the-badge" alt="Search-SWE task gallery"></a>
  <a href="https://huggingface.co/datasets/search-swe/Search-SWE"><img src="https://img.shields.io/badge/HuggingFace-Search--SWE-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Search-SWE dataset on Hugging Face"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-lightgrey?style=for-the-badge&logo=apache&logoColor=white" alt="License: Apache 2.0"></a>
</p>

<p align="center">
  <b>English</b> · <a href="README_zh.md">简体中文</a>
</p>

> *Note: Search-SWE is an ongoing project; tasks, documentation, and results
> are still evolving.*

## 📖 Overview

Search-SWE evaluates whether coding agents can **implement and optimize** real
search systems under fixed resource constraints. Agents inspect an environment,
write and run code, test their systems, and iterate toward an executable
submission. Evaluation measures the behavior of the resulting system, including
retrieval quality, functional correctness, and resource use.

Tasks cover reasoning-assisted retrieval, memory-constrained vector search,
long-document reranking, embedding fine-tuning, and query-encoder alignment.

Each task specifies its inputs, submission interface, evaluation criteria, and
resource budget. See the [benchmark design](docs/benchmark.md) for how
evaluation works, how the repository is organized, and where fixed data and
models come from.

## 🚀 Quick Start

Install the `search-swe` CLI in a Python 3.12+ environment. The PyPI release
installation command is:

```bash
python -m pip install search-swe
```

The package in this checkout is currently unpublished. To test this development
version, clone the repository and use an editable install:

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
python -m pip install -e .
```

### Run with the CLI

```bash
search-swe run
```

The wizard guides you through harness, provider, searchable model selection,
reasoning level and API keys, followed by tasks and sequential or parallel execution. Its
default setting is **Codex + OpenRouter + GPT-6 Luna (max)**. Keys use hidden
input; configuration is saved to the ignored `.env` only after confirmation.
You can also keep entered credentials only for the current run.

Use a native Linux x86_64 Docker host with enough CPU, RAM, disk and optional GPU
capacity. The CLI restores and checks selected task assets, assigns resources,
and prepares bounded task storage when needed. Those tasks require root/sudo
and FUSE; see [host setup](docs/evaluation.md#bounded-task-storage).

After configuration, scripted runs are short:

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

Parallel tasks receive separate CPU sets and GPUs within the selected resource
pool. Results, per-task logs and a `run.json` summary are written to a fresh
`jobs/evaluations/` directory. Use `search-swe list` to browse tasks,
`search-swe configure` to save settings without running, and `--dry-run` to
preview. Task definitions remain in the checkout; use `--repo PATH` when running
an installed CLI from elsewhere.

See the [quick start](docs/quickstart.md), [CLI reference](docs/cli.md), and
[full evaluation guide](docs/evaluation.md) for custom providers, resource pools,
network configuration and the underlying single-task launcher.

### Run through your agent

Install [run-searchswe-evaluation](skills/run-searchswe-evaluation/SKILL.md) into
your coding agent, then tell it which settings and tasks to run. Once this skill
is available on GitHub, use either installer (Codex shown here):

```bash
npx skills add VectorSpaceLab/Search-SWE --skill run-searchswe-evaluation -a codex
```

```bash
gh skill install VectorSpaceLab/Search-SWE skills/run-searchswe-evaluation --agent codex
```

Then ask your agent:

> Use run-searchswe-evaluation with my Search-SWE checkout. Run agentic-search
> and agentic-search-vectorless with Codex + OpenRouter + openai/gpt-6-luna,
> max reasoning and concurrency 2. Reuse my .env, monitor the runs and report
> scores, verifier health and result paths.

The skill guides setup, resource checks, execution and monitoring through the
same CLI. It prompts you to configure missing keys locally. The
[agent evaluation guide](docs/agent-evaluations.md) covers local checkout
installation, other agents, user-wide installation and installer prerequisites.

## 📚 Documentation

| Document | Contents |
| --- | --- |
| [Quick start guide](docs/quickstart.md) | A first CPU evaluation, end to end |
| [Run with your agent](docs/agent-evaluations.md) | Install the evaluation skill and describe settings/tasks |
| [Evaluation guide](docs/evaluation.md) | Credential setup, coding agents, GPU, network policy, and custom providers |
| [Network policy](docs/network-policy.md) | Phase-specific allowlists, default direct gateway, and optional proxy egress |
| [Asset guide](docs/assets.md) | Downloading, verifying, and restoring fixed data and models |
| [Benchmark design](docs/benchmark.md) | Evaluation, repository layout, and data provenance |
| [Contributing guide](docs/contributing.md) | Task-authoring workflow, validation, and PR expectations |

For task descriptions and results, visit the
[project website](https://search-swe.github.io/), maintained in a
[separate repository](https://github.com/search-swe/search-swe.github.io).

## 🤝 Contributing

Contributions are welcome. For new or substantially revised tasks, start with
the workflow and skills in [`.agents/`](.agents/AGENTS.md), including
[`create-searchswe-task`](.agents/skills/create-searchswe-task/SKILL.md) for task authoring
and [`maintain-searchswe-task`](.agents/skills/maintain-searchswe-task/SKILL.md) for
PR review and publication. See the
[contribution entry](CONTRIBUTING.md) and [guide](docs/contributing.md) for validation and PR requirements.

Task authoring includes running a configured coding model, inspecting its
trajectory and evaluation results, and using that feedback to refine the task
setting. Revalidate any changes that affect the task or scoring and report the
final tested revision. If required API keys are missing, the authoring agent
asks the contributor to configure them locally before the trial.

Create tasks directly at `tasks/<task-name>` in your contribution branch. Choose
a descriptive name of at most five lowercase, hyphen-separated words, and use
it for the package and its official data. One PR may add multiple tasks. Review
and validate each package, then merge with a merge commit to preserve original
authors.

Public upstream HF datasets may be used directly with immutable commit pins,
exact filenames, sizes and SHA-256 hashes. Verify downloads, provenance and usage
terms before merging; official re-upload is optional. When official publication
is needed, publish under `tasks/<task-name>/` and pin the merged HF SHA first.
Use `--task <task-name>` for downloads and local trials.

## Citation

TBA
