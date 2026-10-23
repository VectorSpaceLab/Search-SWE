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
| Hidden queries | 4200 |

Author: Bingyu. Version: 0.1.0. Published task package; the saved coding-agent result is recorded in RUN_RESULTS.md.

Build an offline Qwen3-0.6B-based system for categorical choices, Boolean
judgments, and ordinal ratings. This task follows the user's revised OpenJev
plan, rather than the earlier constrained-shopping recommendation proposal.

| Setting | Value |
| --- | --- |
| Public labeled examples | 80,000 across 279 task configurations |
| Choice / Boolean / ordinal examples | 63,434 / 11,882 / 4,684 |
| Hidden evaluation | Seven original 600-row sets, 4,200 total |
| Metric | Mean exact accuracy; no baseline subtraction |
| Development | 6 hours, A100 40GB, 16 CPUs, 32 GiB RAM, 100 GiB storage |
| Startup / complete inference | 120 seconds / 240 seconds |
| Network / judge API | Disabled / none |

`start.sh` and `run.sh` and all runtime artifacts go in `/app/submission`.
The verifier starts the system before exposing test requests, then times the
whole batch. Categorical answers must be menu keys, Boolean answers JSON
booleans, and ordinal answers zero-based integers. Invalid outputs and failed
or timed-out commands score zero. Valid submissions receive the average of
seven dataset accuracies, equal to overall accuracy because each has 600 rows.
The verifier runs submitted code under UID 10001, protects labels and reward
files, and stops all submission-owned processes before reading results.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

The model must generalize across categorical, Boolean and ordinal decision tasks using a fixed example mixture. The held-out suite measures exact decisions across seven equally weighted datasets under offline execution limits.

## Verification Explanation

### Local validation and author records

Author scripts, original downloads, sampling lineage, GPU experiments and all
known-answer fixtures are in
`../../../task_development/decision-model-training`, outside the task package.
The accepted GPU reference structures are `code-embedding-finetuning` and
`query-encoder-alignment` at base `73f1d8b8cac6e0e74669de481bd5c814a975e1a3`.
This task uses deterministic accuracy and entirely offline verification rather
than copying their API or model-judge configuration.

Run from the repository root:

```bash
python -m unittest discover -s tasks/decision-model-training/tests -p 'test_*.py'
python scripts/download_assets.py --task decision-model-training --verify-only
bash -n tasks/decision-model-training/tests/test.sh
```

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task decision-model-training
bash scripts/run_task.sh --task decision-model-training --gpu-device 0 --model YOUR_AGENT_MODEL
```

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

### Sources and preparation

- [OpenJev training mixture](https://huggingface.co/datasets/s1lv3rj1nx/openjev-mixture/tree/e540d97fc37e92b493ceeb536bdb7a01e366bdc3): 323,466 original rows.
- [OpenJev held-out suite](https://huggingface.co/datasets/s1lv3rj1nx/openjev-heldout/tree/fc5fe530405de8de02e983adbc5b10795618979c): AG News, Banking77, Civil Comments toxicity, CLINC OOS, HelpSteer helpfulness, MASSIVE intent, SST5.
- [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca): exact files verified against the user-supplied local model; Apache-2.0.
- [OpenJev implementation](https://github.com/S1LV3RJ1NX/openjev/tree/91847b4c678f7d9330d8f3475e24c72c7fef73c2): author-side format and contamination checks; not provided as a solution.

Sample without replacement within every source task configuration, seed
20261014. Proportional largest-remainder allocation yields exactly 80,000 rows,
with 8–742 examples per configuration. Before sampling, exclude two training
rows whose normalized state occurs in the hidden suite. The original 4,200
hidden states, questions, option descriptions/order and typed labels are
preserved. Flatten per-example option overrides into each example's question
schema. Neither new labels nor synthetic questions are generated. The upstream
alias guard and normalized-state overlap check pass. No separate public
validation split or baseline implementation is supplied.

OpenJev's assembly is Apache-2.0; constituent datasets retain their own terms.
Its held-out card explicitly flags unclear redistribution rights for AG News
and SST5. The training mixture also does not supply a complete license audit of
all underlying datasets. This package makes no claim that every row is cleared for republication.
Unresolved constituent terms remain recorded for maintainer review.
