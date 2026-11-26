# Decision Model Training

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `decision-model-training` |
| Version | 1.0.0 |
| Authors | Bingyu |
| Primary metric | Mean exact accuracy across seven equally sized datasets |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 480 s |
| Dataset | OpenJev mixture and held-out suite |
| Public queries | 0 |
| Hidden queries | 4200 |

## Overview

Author: Bingyu. Published task package; the saved coding-agent result is recorded in RUN_RESULTS.md.

Build an offline Qwen3-0.6B-based system for categorical choices, Boolean judgments, and ordinal ratings. This task follows the user's revised OpenJev plan, rather than the earlier constrained-shopping recommendation proposal.

| Setting | Value |
| --- | --- |
| Public labeled examples | 80,000 across 279 task configurations |
| Choice / Boolean / ordinal examples | 63,434 / 11,882 / 4,684 |
| Hidden evaluation | Seven original 600-row sets, 4,200 total |
| Metric | Mean exact accuracy; no baseline subtraction |
| Development | 6 hours, A100 40GB, 16 CPUs, 32 GiB RAM, 100 GiB storage |
| Startup / complete inference | 120 seconds / 240 seconds |
| Network / judge API | Disabled / none |

`start.sh` and `run.sh` and all runtime artifacts go in `/app/submission`. The verifier starts the system before exposing test requests, then times the whole batch. Categorical answers must be menu keys, Boolean answers JSON booleans, and ordinal answers zero-based integers. Invalid outputs and failed or timed-out commands score zero. Valid submissions receive the average of seven dataset accuracies, equal to overall accuracy because each has 600 rows. The verifier runs submitted code under UID 10001, protects labels and reward files, and stops all submission-owned processes before reading results.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

The model must generalize across categorical, Boolean and ordinal decision tasks using a fixed example mixture. The held-out suite measures exact decisions across seven equally weighted datasets under offline execution limits.

## Verification Explanation

### Local validation and author records

Author scripts, original downloads, sampling lineage, GPU experiments and all known-answer fixtures are in `../../../task_development/decision-model-training`, outside the task package. Verification uses deterministic accuracy and runs entirely offline.

Run from the repository root:

```bash
python -m unittest discover -s tasks/decision-model-training/tests -p 'test_*.py'
python scripts/assets/download_assets.py --task decision-model-training --verify-only
bash -n tasks/decision-model-training/tests/test.sh
```

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health.

## Running the Task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation/runtime.md), then run:

```bash
python scripts/assets/download_assets.py --task decision-model-training
bash scripts/evaluation/run_task.sh --task decision-model-training --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## References

- **Task source** — [OpenJev](https://openjev.com/)
- **Data source** — OpenJev training mixture and seven held-out decision datasets.
- **Model source** — [Qwen3-0.6B at revision c1899de](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca), Apache-2.0.
- **Provenance details** — [Upstream revisions, sampling, and constituent dataset terms](SOURCES.md)
