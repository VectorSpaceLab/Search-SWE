# Constrained Long-document Reranking

Improve long-document ranking without changing the candidate pool or the relevance model.

**Task:** `task-2-1` · **Mode:** Optimization · **Metric:** Accuracy@5

## Overview

A relevant passage in a long document may lie far beyond the first 512 model
tokens. Simply truncating every candidate can therefore discard the evidence
needed to rank it correctly.

This task starts from a fixed reranking pipeline for NarrativeQA retrieval.
The system receives a BM25 Top-100 candidate pool and must use the supplied
BGE reranker. The engineering opportunity is in how documents are prepared,
which windows are scored, and how local scores inform a document-level decision.
Finding more evidence must remain practical within the runtime budget.

## What This Task Tests

- Handling long documents with a short-input cross-encoder.
- Selecting useful document windows and aggregating their evidence.
- Improving preprocessing and inference without altering learned model behavior.
- Preserving candidate-set identity across a multi-stage ranking pipeline.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | A 355-document long-document corpus |
| `data/validation/` | 100 public queries, fixed candidates, and relevance labels |
| `models/bge-reranker-large/` | The pinned `BAAI/bge-reranker-large` model |
| `environment/starter/` | An editable build/query pipeline |

Downloaded data and models are mounted read-only under `/task/data` and
`/task/models`. The hidden evaluation contains 100 disjoint queries.
[Starter notes](environment/starter/README.md) describe the initial implementation.

### Fixed Components and Allowed Changes

The candidate documents and reranker model, tokenizer, and configuration are
fixed. The agent may optimize preprocessing, window selection, score aggregation,
caching, and runtime organization. It may not retrieve additional candidates,
replace or train the model, distill it, or modify its weights through quantization.

The Docker mounts place the model at `/task/models/bge-reranker-large`.
The introductory model path in `instruction.md` currently contains a typo;
the mounted path and runtime configuration are the operational reference.

### Environment and Resource Limits

The CPU Python 3.12 environment provides 16 CPUs, 64 GiB memory, 100 GiB storage,
and no GPU. The agent has two hours and the Harbor verifier 80 minutes.
The grader's build and run caps are 1,800 and 3,600 seconds respectively,
but these stages and the integrity check must still fit inside the overall
verifier phase; their individual maxima are not additive allowances.

## Submission Contract

The deliverable is `/app/build.sh` and `/app/run.sh` with the implementation
needed to rebuild preprocessing artifacts and serve reranking requests.
Each question returns five ranked document IDs and scores from its original
candidate pool.

The verifier uses a separate environment and unprivileged submission execution.
The index directory is supplied by the caller. Consult
[instruction.md](instruction.md) for the complete CLI and result format.

## Evaluation

### Search Quality

A hidden query is a hit if a relevant document is among the five returned
candidates. Accuracy@5 is the fraction of hits over all hidden queries.
Unlike the implementation tasks' all-query gates, valid runs receive a
continuous quality score.

### Correctness and Resource Gates

The verifier checks executable behavior, complete outputs, valid ranking
fields, candidate membership, and compliance with the fixed-model rules.
Retrieval outside the pool is not a valid way to improve this task's score.

### Integrity Checks and Final Reward

A separate trajectory judge checks task compliance. Final reward equals
Accuracy@5 only when evaluation is valid and the judge passes; otherwise zero.
The model being optimized around is the fixed reranker, not the trajectory judge.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Download both data and model assets with the command below. Configure the
verifier's integrity judge separately from the coding agent. The submission
uses the local reranker and does not need external reranking-service credentials.

```bash
python scripts/download_assets.py --task task-2-1
bash scripts/run_task.sh --task task-2-1 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-2-1/`.
Replace `YOUR_AGENT_MODEL` with your configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

## Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [task.toml](task.toml) | Task identity, artifact collection, and phase budgets |
| [assets.json](assets.json) | Fixed asset paths, immutable revisions, and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and task environment |
| [Environment configuration](environment/docker-compose.yaml) | Read-only mounts and hardware requests |
| [Verifier](tests/) | Execution, output validation, and scoring implementation |
| [Starter notes](environment/starter/README.md) | Initial pipeline and local validation guidance |
| [Verifier notes](tests/README.md) | Additional verification details |
