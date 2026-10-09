# Benchmark design

This document explains how tasks are evaluated, how the repository is organized,
and where fixed data and model inputs come from. For setup and execution, start
with the [quick start guide](quickstart.md) and the [evaluation guide](evaluation.md).
A summary of the engineering objectives lives in the
[project README](../README.md).

## Evaluation

Tasks use sandboxed environments and a separate verifier. Depending on the
task, verification checks:

- **Functionality:** required interfaces, valid outputs, and successful execution.
- **Retrieval quality:** performance on held-out queries, using the task's specified metric and thresholds.
- **Efficiency:** build time, query latency, memory use, or other resource limits.
- **Integrity:** compliance with task rules, including restrictions on hidden evaluation data and permitted resources.

Scoring is defined per task. Some tasks require all correctness and resource
checks to pass; others measure improvement over a supplied baseline.

Each task specifies its inputs, submission interface, evaluation criteria, and
resource budget. Depending on the task, agents receive a corpus, public
validation examples, starter code, or fixed model assets. Task-specific rules
govern access to models, tools, and network services.

## Repository Structure

The repository separates task code from downloadable data and model assets.

```text
Search-SWE/
├── README.md
├── README_zh.md
├── LICENSE
├── assets/                       # Hero image used by the README
├── docker/                       # Reproducible CPU and GPU base-image contexts
├── tasks/
│   ├── <task-name>/              # Task package
│   │   ├── instruction.md        # Agent-facing task specification
│   │   ├── task.toml             # Task and environment configuration
│   │   ├── assets.json           # Fixed input file sizes and checksums
│   │   ├── environment/          # Dockerfile, starter code, and environment docs
│   │   └── tests/                # Verifier and grading code
│   └── ...                       # Additional task packages
├── task-submissions/             # New task packages before same-PR promotion
│   └── <task-name>/              # Same name retained under tasks/ after review
├── scripts/
│   ├── requirements.txt          # Host-side launcher and asset dependencies
│   ├── download_assets.py        # Download and verify fixed data/model inputs
│   ├── download_models.py        # Download fixed models only
│   ├── check_release.py          # Check package structure and asset mappings
│   ├── run_task.sh               # Shared Harbor launcher (Codex, Pi, or Claude Code)
│   └── run_task.py               # Configuration loading and command construction
└── docs/                         # Installation and evaluation guides
```

## Data and Models

Task data is hosted on Hugging Face in
[search-swe/Search-SWE](https://huggingface.co/datasets/search-swe/Search-SWE).
Pretrained weights are downloaded from their original model repositories.

Each task's `assets.json` records its fixed input files, sizes, SHA-256
checksums, and download sources. Runtime data belongs in
`tasks/<task-name>/data/` and fixed models in `tasks/<task-name>/models/`; these
directories are excluded from Git. Dataset and model revisions are pinned to
immutable commits. See the [asset guide](assets.md) for the directory layout,
downloads, and local restoration options.

Dataset provenance, processing details, and licensing information are documented
in the Hugging Face dataset card. Hidden evaluation queries and labels belong in
the task package's `tests/data/` and are kept separate from the downloadable
task data.
