# Code Embedding Fine-tuning

Adapt a fixed embedding backbone to code retrieval and measure the resulting quality gain.

**Task:** `code-embedding-finetuning` · **Metric:** Held-out Accuracy@1 improvement

## Overview

A general embedding model may not organize natural-language requests and code
documents in the way a code-search application needs. This task asks a coding
agent to improve that alignment using supplied supervised examples.

The output is a trained checkpoint, rather than a custom search service.
The verifier applies the same embedding and exact-search procedure to the
original backbone and the submission. This isolates improvement in the learned
representation from changes to indexing, candidate selection, or serving code.

## What This Task Tests

- Designing a useful domain adaptation process from limited supervised data.
- Choosing training objectives and sampling strategies that generalize.
- Preserving model compatibility while updating its parameters.
- Producing a reproducible, self-contained offline checkpoint.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | Code-retrieval documents |
| `data/train.jsonl` | 5,000 supervised training examples |
| `data/validation/` | Ten public queries and relevance labels |
| `models/bge-base-en-v1.5/` | The pinned original backbone |
| `environment/starter/train.sh` | Starting point for the training workflow |

The hidden evaluation contains 200 queries. Public data and the backbone are
mounted read-only under `/task/data` and `/task/models`; hidden questions and
labels are excluded from the agent environment.

### Fixed Components and Allowed Changes

Training choices and model weights may change. The backbone architecture,
model class, structural configuration, parameter names, shapes, and count must
remain compatible. The verifier owns the embedding and exact-retrieval procedure.

Development uses the supplied offline data and packages. External checkpoints,
datasets, labels, and answer mappings are not permitted; see the
[resource policy](environment/docs/available_resources.md).

### Environment and Resource Limits

The runtime uses Python 3.12 with CUDA-enabled PyTorch. It is configured for
8 CPUs, 32 GiB memory, and 100 GiB storage. The environment and verifier
Compose files and `task.toml` explicitly request **one NVIDIA GPU**.
For local Docker, the shared launcher works around Harbor 0.22.0's GPU
capability preflight with `--override-gpus 0`; the Compose reservations still
provide the GPU to both containers.

The agent phase has 12 hours. Task-specific verification has one hour,
followed by a separately bounded integrity check, within an 85-minute Harbor
verifier phase. The submission training environment is offline; the coding
agent and private judge have their own API configuration.

## Submission Contract

The artifact is a complete checkpoint at `/app/submission/model`, including
the files needed by standard Transformers tokenizer and model loaders with
`local_files_only=True`. Only `/app/submission` is transferred for evaluation.

There is no submitted retrieval CLI to optimize here: the verifier loads the
checkpoint and executes its own fixed search procedure. Full compatibility
requirements are in [instruction.md](instruction.md).

## Evaluation

### Search Quality

Accuracy@1 measures whether the highest-ranked code document is relevant.
The grader evaluates both checkpoints on identical hidden queries, using
normalized first-token embeddings, the same token limit, and exact inner-product
search. The base task reward is:

```text
max(0, submitted Accuracy@1 - original-backbone Accuracy@1)
```

This is an absolute gain on the 0–1 accuracy scale, not a percentage-relative
improvement and not the submitted accuracy by itself.

### Correctness and Resource Gates

The checkpoint must load offline and match the backbone's structural signature.
Invalid models, failed evaluation, and timeouts receive zero. Training-side
validation results do not replace the verifier's independent comparison.

### Integrity Checks and Final Reward

A trajectory audit gates the nonnegative quality gain. A failed audit or
invalid evaluation produces zero, regardless of the apparent training result.
The audit uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 with
verifier-only DeepSeek endpoint and key settings.

## Running This Task

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Prepare an NVIDIA-capable Docker host and the GPU base image referenced by the
Dockerfiles. Configure the integrity judge as well as the coding agent.
The asset downloader restores both training data and the fixed backbone.

```bash
python scripts/download_assets.py --task code-embedding-finetuning
bash scripts/run_task.sh --task code-embedding-finetuning --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/code-embedding-finetuning/`.
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
| [Training starter](environment/starter/train.sh) | Initial training entry point |
| [Resource policy](environment/docs/available_resources.md) | Offline development restrictions |
