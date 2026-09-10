# Search-SWE

[English](README.md) | [Chinese](README_zh.md)

**Benchmarking coding agents on search-system engineering.**

[![Project Website](https://img.shields.io/badge/github-Search--SWE-blue?logo=github)](https://search-swe.github.io/) [![Task Gallery](https://img.shields.io/badge/github-Task_Gallery-blue?logo=github)](https://search-swe.github.io/tasks.html) [![Data](https://img.shields.io/badge/HuggingFace-Search--SWE-blue?logo=huggingface)](https://huggingface.co/datasets/search-swe/Search-SWE) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


Search-SWE evaluates whether coding agents can **implement, optimize, and repair** search systems under fixed resource constraints. Agents inspect an environment, write and run code, test their systems, and iterate toward an executable submission. Evaluation measures the behavior of the resulting system, including retrieval quality, functional correctness, and resource use.

> In progress

## 📝 Task Categories

| Category | Agent objective | Example problems |
| --- | --- | --- |
| Implementation | Build a search capability from a task specification. | Reasoning-assisted retrieval; memory-constrained vector search. |
| Optimization | Improve an existing system within task-specific constraints. | Long-document reranking; embedding fine-tuning; query-encoder optimization. |
| Repair | Diagnose and fix failures in a search system. | Retrieval pipeline bugs; model inference compatibility. |

Each task specifies its inputs, submission interface, evaluation criteria, and resource budget. Depending on the task, agents receive a corpus, public validation examples, starter code, or fixed model assets. Task-specific rules govern access to models, tools, and network services.

## 📊 Evaluation

Tasks use sandboxed environments and a separate verifier. Depending on the task, verification checks:

- **Functionality:** required interfaces, valid outputs, and successful execution.
- **Retrieval quality:** performance on held-out queries, using the task's specified metric and thresholds.
- **Efficiency:** build time, query latency, memory use, or other resource limits.
- **Integrity:** compliance with task rules, including restrictions on hidden evaluation data and permitted resources.

Scoring is defined per task. Some tasks require all correctness and resource checks to pass; others measure improvement over a supplied baseline.

## 🧩 Repository Structure

The repository separates task code from downloadable data and model assets.

```text
Search-SWE/
├── README.md
├── README_zh.md
├── LICENSE
├── tasks/
│   ├── <task-id>/                # Task package
│   │   ├── instruction.md        # Agent-facing task specification
│   │   ├── task.toml             # Task and environment configuration
│   │   ├── assets.json           # Fixed input file sizes and checksums
│   │   ├── environment/          # Dockerfile, starter code, and environment docs
│   │   └── tests/                # Verifier and grading code
│   └── ...                       # Additional task packages
├── scripts/
│   ├── download_assets.py        # Download and verify fixed data/model inputs
│   ├── download_models.py        # Download fixed models only
│   ├── check_release.py          # Check package structure and asset mappings
│   ├── run_task.sh               # Shared Harbor launcher (Codex agent)
│   └── run_task.py               # Configuration loading and command construction
└── docs/                         # Installation and evaluation guides
```

## 🧠 Data and Models

Task data is hosted on Hugging Face in [search-swe/Search-SWE](https://huggingface.co/datasets/search-swe/Search-SWE). Pretrained weights are downloaded from their original model repositories.

Each task's `assets.json` records its fixed input files, sizes, SHA-256 checksums, and download sources. Runtime data belongs in `tasks/<task-id>/data/` and fixed models in `tasks/<task-id>/models/`; these directories are excluded from Git. Dataset and model revisions are pinned to immutable commits. See the [asset guide](docs/assets.md) for the directory layout, downloads, and local restoration options.

Dataset provenance, processing details, and licensing information are documented in the Hugging Face dataset card. Hidden evaluation queries and labels belong in the task package's `tests/data/` and are kept separate from the downloadable task data.

## 🚀 Getting Started

Clone the repository:

```bash
git clone https://github.com/VectorSpaceLab/Search-SWE.git
cd Search-SWE
```

With Python 3.12 or newer, install the download dependency and restore fixed inputs:

```bash
python -m pip install -r scripts/requirements-assets.txt
python scripts/download_assets.py --task all --kind data
python scripts/download_models.py --task all
```

Use `--task task-2-1`, for example, to download one task. The downloader verifies sizes and SHA-256 checksums and reuses valid existing files. See the [asset guide](docs/assets.md) for verification and cache options.

Running the benchmark also requires a compatible Harbor installation, Docker, the referenced base images, and task-specific CPU/GPU resources.

The [launcher guide](docs/quickstart.md) describes the prerequisites, independent agent and verifier API configuration, optional container proxies, and launch commands.

For task descriptions, visit the [project website](https://search-swe.github.io/). The website is maintained in a [separate repository](https://github.com/search-swe/search-swe.github.io).

## Citation

## Acknowledgments
This repository and documentation page are maintained by the VectorSpaceLab.
