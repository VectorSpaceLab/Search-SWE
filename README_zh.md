# Search-SWE

[英文](README.md) | [简体中文](README_zh.md)

**面向搜索系统工程的编码智能体评测基准。**

[项目主页](https://search-swe.github.io/) · [任务展示](https://search-swe.github.io/tasks.html)

Search-SWE 评估编码智能体能否在固定资源约束下**实现、优化和修复**搜索系统。智能体需要检查环境、编写并运行代码、测试系统，最终提交可执行的实现。评测关注系统的实际表现，包括检索质量、功能正确性和资源消耗。

> In progress

## 任务类别

| 类别 | 智能体目标 | 示例问题 |
| --- | --- | --- |
| 实现 | 根据任务要求构建搜索能力。 | 推理辅助检索、内存受限的向量搜索。 |
| 优化 | 在任务约束下改进已有系统。 | 长文档重排序、嵌入模型微调、查询编码器优化。 |
| 修复 | 定位并修复搜索系统中的问题。 | 检索流程缺陷、模型推理兼容性。 |

每个任务都明确规定输入、提交接口、评测标准和资源预算。根据任务需要，智能体可以获得语料、公开验证样例、起始代码或固定模型资源。模型、工具和网络服务的使用范围由具体任务规定。

## 评测方式

任务在隔离环境中运行，由独立的验证器进行评测。具体检查内容因任务而异，包括：

- **功能正确性：** 接口符合要求、输出有效、程序能够成功执行。
- **检索质量：** 按任务指定的指标和阈值，在保留的评测查询上测量表现。
- **运行效率：** 构建时间、查询延迟、内存占用及其他资源限制。
- **规则遵守情况：** 是否遵守隐藏评测数据访问限制和允许使用的资源范围。

评分规则由各任务定义。有些任务要求同时通过正确性与资源限制检查，有些任务则衡量相对于固定基线的改进。

## 仓库结构

仓库将任务代码与需要下载的数据、模型分开存放。

```text
Search-SWE/
├── README.md
├── README_zh.md
├── LICENSE
├── tasks/
│   ├── <task-id>/                # 任务包
│   │   ├── instruction.md        # 面向智能体的任务说明
│   │   ├── task.toml             # 任务与环境配置
│   │   ├── assets.json           # 固定资源的大小、校验值和下载来源
│   │   ├── environment/          # Dockerfile、起始代码和环境说明
│   │   └── tests/                # 验证器和评分代码
│   └── ...                       # 其他任务包
├── scripts/
│   ├── download_assets.py        # 下载并校验固定数据和模型
│   ├── download_models.py        # 单独下载固定模型
│   ├── check_release.py          # 检查发布目录与资源映射
│   ├── run_task.sh               # 统一 Harbor 启动入口，使用 Codex 智能体
│   └── run_task.py               # 加载配置并构造运行命令
└── docs/                         # 安装、运行和评测说明
```

## 数据与模型

任务数据托管在 Hugging Face 的 [search-swe/Search-SWE](https://huggingface.co/datasets/search-swe/Search-SWE) 数据集中。预训练权重从原始模型仓库下载。

每个任务的 `assets.json` 记录固定输入文件的路径、字节数、SHA-256 校验值和下载来源。公开数据恢复到 `tasks/<task-id>/data/`，固定模型恢复到 `tasks/<task-id>/models/`；这两个目录均被 Git 忽略。数据和模型来源均固定到具体的提交版本。目录约定和下载选项见[资源说明](docs/assets.md)。

数据来源、处理方式和许可信息见 Hugging Face 数据集说明。隐藏评测查询和标签放在任务包的 `tests/data/` 中，与可下载的任务数据分开存放。

## 开始使用

克隆仓库：

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
```

使用 Python 3.12 或更新版本，安装下载依赖并恢复固定资源：

```bash
python -m pip install -r scripts/requirements-assets.txt
python scripts/download_assets.py --task all --kind data
python scripts/download_models.py --task all
```

如需单个任务，可以将 `--task all` 改为 `--task task-2-1`。下载器会核对文件大小和 SHA-256，并复用已通过校验的文件。校验与缓存选项见[资源说明](docs/assets.md)。

运行评测还需要兼容的 Harbor、Docker、任务引用的基础镜像，以及符合要求的 CPU/GPU 资源。

[启动说明](docs/quickstart.md)介绍了运行前提、智能体与验证器的独立 API 配置、可选容器代理和启动命令。

任务介绍可在[项目主页](https://search-swe.github.io/)查看。主页由[独立仓库](https://github.com/search-swe/search-swe.github.io)维护。
