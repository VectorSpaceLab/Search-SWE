<p align="center">
  <img src="assets/hero.png" alt="Search-SWE — Benchmarking coding agents on search-system engineering">
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

| Mode | Agent objective | Example problems |
| --- | --- | --- |
| Implementation | Build a working search capability from a task specification. | Reasoning-assisted retrieval; memory-constrained vector search. |
| Optimization | Improve search quality or efficiency within fixed constraints. | Long-document reranking; embedding fine-tuning; query-encoder optimization. |

Each task specifies its inputs, submission interface, evaluation criteria, and
resource budget. See the [benchmark design](docs/benchmark.md) for how
evaluation works, how the repository is organized, and where fixed data and
models come from.

## 🚀 Quick Start

This walkthrough runs `task-1-1` on CPU with the Pi coding agent and DeepSeek
Flash. Search-SWE requires Python 3.12 or newer and Docker with the CPU, memory,
storage, and optional GPU capacity of the task you select.

### 1. Install the host tools

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
python -m pip install -r scripts/requirements.txt
```

`scripts/requirements.txt` provides the pinned Harbor launcher and the Hugging
Face asset client. Run the command in any existing Python 3.12+ environment;
an isolated venv or Conda environment is recommended if you do not already use
one, but no particular environment manager is required. Task-specific Python
packages are installed inside Docker.

### 2. Restore the task inputs

```bash
python scripts/download_assets.py --task task-1-1
python scripts/download_assets.py --task task-1-1 --verify-only
```

The downloader checks sizes and SHA-256 checksums and reuses valid files.

### 3. Configure the agent and verifier

The tracked template lists every supported credential and explains when each
one is needed. Copy it once; put real secrets only in the ignored `.env` file:

```bash
cp .env.example .env
chmod 600 .env
```

For this Pi + DeepSeek walkthrough, set these four values in `.env` and leave
unneeded groups empty:

```dotenv
AGENT_MODEL=deepseek/deepseek-flash
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
VERIFIER_OPENAI_BASE_URL=https://api.deepseek.com/
VERIFIER_OPENAI_API_KEY=YOUR_DEEPSEEK_KEY
```

`DEEPSEEK_API_KEY` authenticates the Pi agent for `deepseek/deepseek-flash`.
The `VERIFIER_*` pair runs the independent `deepseek-flash` trajectory judge
through RewardKit 0.2.0 and is required by every task except `task-2-4`. The
same DeepSeek key may be assigned to both variables, but the launcher passes
the verifier copy only to the verifier container.

For other runs, fill only the matching sections already present in `.env`:

- Pi + GLM-5.3-Flash: `AGENT_MODEL=zai/glm-5.3-flash` and `ZAI_API_KEY`.
- Codex: `AGENT_MODEL`, `AGENT_OPENAI_BASE_URL`, and `AGENT_OPENAI_API_KEY`.
- Claude Code: `AGENT_MODEL` and `AGENT_ANTHROPIC_API_KEY`; the launcher uses
  only Anthropic's official API.
- Task 1-3: the three `ANSWER_JUDGE_*` values are also required.
- Optional submission APIs: use `TASK_1_1_OPENROUTER_API_KEY`,
  `OPENROUTER_API_KEY`, or `JINA_API_KEY` only for the tasks identified by the
  comments in `.env.example`.

The [evaluation guide](docs/evaluation.md) documents credential isolation,
custom endpoints, proxies, and the complete per-task matrix.

### 4. Run with Pi and DeepSeek Flash

```bash
bash scripts/run_task.sh --task task-1-1 --agent pi \
  --thinking xhigh --dry-run

bash scripts/run_task.sh --task task-1-1 --agent pi \
  --thinking xhigh \
  --output jobs/task-1-1-pi-deepseek
```

The dry run only prints the Harbor command. The second command builds the task
images, runs the agent and the separate verifier, and writes the reward and job
records under `jobs/task-1-1-pi-deepseek`.

<details>
<summary><strong>Alternative agent examples</strong></summary>

These examples reuse the downloaded task inputs and the `VERIFIER_*` pair above.
Configure only the coding-agent credential group for the option you choose.

#### Pi and Z.AI GLM-5.3-Flash

In `.env`, change the agent model and fill its matching key. Keep the
`VERIFIER_*` DeepSeek settings because the RewardKit judge does not change:

```dotenv
AGENT_MODEL=zai/glm-5.3-flash
ZAI_API_KEY=YOUR_ZAI_KEY
```

```bash
bash scripts/run_task.sh --task task-1-1 --agent pi \
  --thinking xhigh \
  --output jobs/task-1-1-pi-glm
```

#### Codex and a GPT model

Set the model name accepted by your GPT-compatible endpoint and its credentials:

```dotenv
AGENT_MODEL=YOUR_GPT_MODEL
AGENT_OPENAI_BASE_URL=https://your-agent-endpoint.example/v1
AGENT_OPENAI_API_KEY=YOUR_AGENT_KEY
```

```bash
bash scripts/run_task.sh --task task-1-1 --agent codex \
  --reasoning-effort xhigh --output jobs/task-1-1-codex
```

Omit `--reasoning-effort` when the selected model or provider does not support
it.

#### Claude Code and the official Anthropic API

Claude Code 2.1.273 is preinstalled in every task image. Set an Anthropic model
available to your API account and the dedicated coding-agent key:

```dotenv
AGENT_MODEL=claude-sonnet-4-6
AGENT_ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
```

```bash
bash scripts/run_task.sh --task task-1-1 --agent claude-code \
  --reasoning-effort high --output jobs/task-1-1-claude
```

The shared launcher supports API-key authentication to `api.anthropic.com`;
custom gateways, subscription OAuth, Bedrock, Vertex, ACP, and custom Claude
settings are intentionally outside the initial support scope. The
[quick start guide](docs/quickstart.md) covers the default Codex path;
the [evaluation guide](docs/evaluation.md) covers the per-task credential and
hardware matrix plus GPU, network-policy, and custom-provider options.

</details>

## 📚 Documentation

| Document | Contents |
| --- | --- |
| [Quick start guide](docs/quickstart.md) | A first CPU evaluation, end to end |
| [Evaluation guide](docs/evaluation.md) | Per-task credentials, coding agents, GPU, network policy, and custom providers |
| [Network policy](docs/network-policy.md) | Harbor egress modes and exact per-task host allowlists |
| [Asset guide](docs/assets.md) | Downloading, verifying, and restoring fixed data and models |
| [Benchmark design](docs/benchmark.md) | Evaluation, repository layout, and data provenance |
| [Contributing guide](docs/contributing.md) | Task-authoring workflow, validation, and PR expectations |

For task descriptions and results, visit the
[project website](https://search-swe.github.io/), maintained in a
[separate repository](https://github.com/search-swe/search-swe.github.io).

## 🤝 Contributing

Contributions are welcome. For new or substantially revised tasks, start with
the workflow and skills in [`.agents/`](.agents/AGENTS.md), including
[`create-searchswe-task`](.agents/skills/create-searchswe-task/SKILL.md) for submissions
and [`maintain-searchswe-task`](.agents/skills/maintain-searchswe-task/SKILL.md) for
PR review and promotion. See the
[contribution entry](CONTRIBUTING.md) and [guide](docs/contributing.md) for validation and PR requirements.

New tasks use
`task-submissions/<first-name-slug>/<category>-x-<positive-ordinal>` (your ASCII
first name, **not** username). One PR may add multiple tasks, all under exactly
one contributor namespace; temporary ordinals are unique within category and
are not final IDs or reusable after promotion in that PR. A different same-name
contributor explicitly chooses `alice-2`. Maintainers assign final IDs near
merge, then make separate pure
`git mv` and finalization commits for every task **in that same PR**. Use
**merge commit only**, not squash/rebase; no unfinished submission enters main.
Development assets may use a personal public HF dataset pinned to a commit SHA.
After final ID assignment, official assets go through an HF community PR or
maintainer mirror; official HF merge and SHA pinning precede the GitHub merge.
Never share official tokens. Explicit `--task-path` supports submission downloads
and local trials; automatic task discovery remains formal-only.

## Citation

TBA
