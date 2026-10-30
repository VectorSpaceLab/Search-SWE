<p align="center">
  <img src="assets/hero.png" alt="Search-SWE——评测编码智能体构建搜索引擎的能力">
</p>

<h1 align="center">
  Search-SWE
  <br>
  <sub>🔍 评测编码智能体构建搜索引擎的能力。 🤖</sub>
</h1>

<p align="center">
  <a href="https://search-swe.github.io/"><img src="https://img.shields.io/badge/Homepage-Search--SWE-0E9B9B?style=for-the-badge&logo=githubpages&logoColor=white" alt="Search-SWE 项目主页"></a>
  <a href="https://search-swe.github.io/tasks.html"><img src="https://img.shields.io/badge/Task_Gallery-Browse-5865F2?style=for-the-badge" alt="Search-SWE 任务展示"></a>
  <a href="https://huggingface.co/datasets/search-swe/Search-SWE"><img src="https://img.shields.io/badge/HuggingFace-Search--SWE-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Hugging Face 上的 Search-SWE 数据集"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-lightgrey?style=for-the-badge&logo=apache&logoColor=white" alt="许可证：Apache 2.0"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

> *Note: Search-SWE 是一个持续演进的项目，任务、文档和评测结果仍在不断更新。*

## 📖 概述

Search-SWE 评估编码智能体能否在固定资源约束下**实现和优化**真实的搜索系统。
智能体需要检查环境、编写并运行代码、测试系统，最终提交可执行的实现。评测关注
系统的实际表现，包括检索质量、功能正确性和资源消耗。

任务涵盖推理辅助检索、内存受限的向量搜索、长文档重排序、嵌入模型微调和
查询编码器对齐等问题。

每个任务都明确规定输入、提交接口、评测标准和资源预算。评测方式、仓库结构和
固定数据与模型的来源见[基准设计](docs/benchmark.md)。

## 🚀 快速开始

在 Python 3.12+ 环境中安装 `search-swe` CLI。发布到 PyPI 后的安装命令为：

```bash
python -m pip install search-swe
```

当前 checkout 中的包尚未发布。测试这个开发版本时，克隆仓库并使用本地可编辑安装：

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
python -m pip install -e .
```

### 通过 CLI 运行

```bash
search-swe run
```

向导会依次引导选择 harness、provider、搜索并选择模型、推理强度和配置 API key，然后多选
任务，选择顺序或并行运行。默认 setting 是 **Codex + OpenRouter + GPT-6 Luna
（max）**。Key 使用隐藏输入；确认后才将配置保存到被 Git 忽略的 `.env`，也可以
选择仅在本次运行使用输入的凭证。

主机需为原生 Linux x86_64 Docker 环境，并具有足够的 CPU、RAM、磁盘和任务所需
GPU。CLI 会自动恢复并校验所选任务的数据、分配资源，以及准备需要的限额存储。
使用限额文件系统的任务需要 root/sudo 和 FUSE，详见
[主机配置](docs/evaluation.md#bounded-task-storage)。

配置完成后，可以直接启动：

```bash
search-swe run reasoning-query-rewriting --yes
search-swe run agentic-search agentic-search-vectorless --concurrency 2 --yes
search-swe run code-embedding-finetuning --gpu-devices 0 --yes
```

并行任务会在所选资源池内分配不同的 CPU 集合和 GPU。结果、各任务日志与
`run.json` 摘要保存在新建的 `jobs/evaluations/` 目录下。使用 `search-swe list`
浏览任务，`search-swe configure` 只保存配置，`--dry-run` 预览配置与命令。
任务定义仍从 checkout 加载；在其他目录运行安装好的 CLI 时可指定 `--repo PATH`。

[快速开始](docs/quickstart.md)、[CLI 文档](docs/cli.md)及
[完整评测指南](docs/evaluation.md)介绍自定义 provider、资源池、网络配置和底层单任务入口。

### 通过自己的 agent 运行

将 [run-searchswe-evaluation](skills/run-searchswe-evaluation/SKILL.md) 安装到
自己的 coding agent，再告诉它要用什么 setting 跑哪些 tasks。这个 skill 发布到
GitHub 后，可任选一种方式安装（以下以 Codex 为例）：

```bash
npx skills add VectorSpaceLab/Search-SWE --skill run-searchswe-evaluation -a codex
```

```bash
gh skill install VectorSpaceLab/Search-SWE skills/run-searchswe-evaluation --agent codex
```

然后告诉 agent：

> 使用 run-searchswe-evaluation 和我的 Search-SWE checkout，以 Codex + OpenRouter +
> openai/gpt-6-luna、max 推理强度，运行 agentic-search 和 agentic-search-vectorless，
> 并发上限为 2。复用我的 .env，跟踪运行进展，最后汇报得分、verifier 状态和结果路径。

Skill 会指导 agent 使用同一个 CLI 完成配置、资源检查、启动和监控；缺少 key 时，
会提醒你在本地配置。[Agent 评测指南](docs/agent-evaluations.md)提供从本地 checkout
安装、选择其他 agent、用户级安装及安装工具的环境要求。

## 📚 文档索引

| 文档 | 内容 |
| --- | --- |
| [快速开始指南](docs/quickstart.md) | 完整的一次 CPU 评测流程 |
| [通过 agent 运行](docs/agent-evaluations.md) | 安装评测 skill，并指定 settings 和 tasks |
| [评测指南](docs/evaluation.md) | 凭证配置、编码智能体、GPU、网络策略和自定义模型服务 |
| [网络权限](docs/network-policy.md) | 各阶段的 host allowlist、默认直连网关与可选代理出口 |
| [资源说明](docs/assets.md) | 固定数据与模型的下载、校验和恢复 |
| [基准设计](docs/benchmark.md) | 评测方式、仓库结构和数据来源 |
| [贡献指南](docs/contributing.md) | 任务创作流程、验证要求和 PR 说明 |

任务介绍和评测结果可在[项目主页](https://search-swe.github.io/)查看，主页由
[独立仓库](https://github.com/search-swe/search-swe.github.io)维护。

## 🤝 参与贡献

欢迎参与贡献。创建新任务或大幅修改已有任务时，请先使用 [`.agents/`](.agents/AGENTS.md)
中的工作流和 skills，包括
[`create-searchswe-task`](.agents/skills/create-searchswe-task/SKILL.md)（任务投稿）和
[`maintain-searchswe-task`](.agents/skills/maintain-searchswe-task/SKILL.md)（PR 审查与发布）。验证要求和
PR 说明见[贡献入口](CONTRIBUTING.md)与[贡献指南](docs/contributing.md)。

任务构建还包括使用配置好的编码模型试跑，检查执行轨迹和评测结果，并根据反馈
完善任务设定。影响任务要求或评分的修改需要重新验证，并记录最终测试的版本。
如果缺少必需的 API key，负责构建任务的智能体应在试跑前提醒贡献者在本地配置。

在贡献分支中直接将新任务放在 `tasks/<task-name>`。名称使用不超过五个词的
小写连字符短语，任务包与官方数据使用同一名称。一个 PR 可以包含多个任务；
逐一完成审查与验证后，使用 merge commit 保留原作者历史。

可以直接使用上游公开 HF 数据集，固定完整 commit SHA、文件路径、大小和 SHA-256。
合并前验证下载、来源和使用条件，无须强制重新上传到官方仓库。需要官方发布时，
将输入放在 `tasks/<task-name>/` 下，并先固定官方已合并的 HF SHA。
使用 `--task <task-name>` 下载数据和进行本地试跑。

## 引用

TBA
