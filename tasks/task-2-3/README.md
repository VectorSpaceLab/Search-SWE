# Query-side Encoder Alignment

Improve a compact query encoder against a document collection whose embeddings cannot change.

**Task:** `task-2-3` · **Mode:** Optimization · **Metric:** Accuracy@1 with a runtime gate

## Overview

Replacing or tuning a query encoder does not automatically preserve its
compatibility with an existing document index. This task fixes the document
embeddings and asks the agent to improve retrieval from the query side using
the supplied Qwen3-Embedding-0.6B backbone.

The system must be accurate and materially faster than a larger teacher-side
reference. It is therefore a joint representation and execution problem:
a query vector must land in the right document space, and the complete query
pipeline must stay within the relative runtime budget.

## What This Task Tests

- Aligning a compact query representation with a frozen document-vector space.
- Preserving document identities and vector-row correspondence.
- Balancing query encoding quality with end-to-end execution time.
- Packaging deterministic inference and retrieval for offline verification.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/doc.npy` | 8,674 fixed float32 document vectors, each 2,560-dimensional |
| `data/corpus.jsonl` | The document identities corresponding to vector rows |
| `data/validation/` | 100 public queries and labels |
| `models/Qwen3-Embedding-0.6B/` | The required query-side backbone |
| `environment/starter/` | Teacher-side reference runner and validation notes |

The manifest also restores the Qwen3-Embedding-4B reference assets.
Reference-model files have separate access permissions; their presence in the
download set does not make them a permissible replacement submission backbone.
There are 100 hidden evaluation queries, isolated from the agent environment.

### Fixed Components and Allowed Changes

The query-side system may be adapted within the supplied 0.6B backbone
requirement. Document vectors must not be modified, re-encoded, replaced,
or reordered. Development-time network access may support documentation and
tools, but not replacement backbones, evaluation labels, or external retrieval
results. The final submission must be self-contained and offline.

### Environment and Resource Limits

The Python 3.12 runtime uses CUDA-enabled PyTorch, 8 CPUs, 32 GiB memory, and
100 GiB storage. Both Compose configurations request **one NVIDIA GPU**,
despite the generic `task.toml` field currently reading `gpus = 0`.

The agent has 12 hours. Task-specific verification has 70 minutes inside
the 95-minute Harbor verifier phase, with the integrity check bounded separately.
The candidate must finish within **60% of the measured reference runtime**.
The evaluation runner also caps each reference/candidate run at 1,800 seconds.

## Submission Contract

The complete deliverable lives under `/app/submission` and includes an executable
`run.sh`. It accepts document vectors and query files, and returns one ranked
document per query. The verifier copies only this directory.

Outputs must be deterministic and preserve query order, and execution must
leave no background processes. [instruction.md](instruction.md) defines the
complete interface; no separate submitted build step is required.

## Evaluation

### Search Quality

The grader reports Accuracy@1 and converts candidate accuracy into a normalized
reward using a fixed anchor:

```text
quality reward = clamp((candidate Accuracy@1 - 0.31) / 0.69, 0, 1)
```

The measured starter accuracy is diagnostic. It is not subtracted in this
formula: `0.31` is the fixed accuracy anchor.

### Correctness and Resource Gates

Candidate wall time must be at most `0.60 × starter wall time`, measured on the
same hidden workload. Missing the gate makes reward zero even if accuracy is
high. Vector checksums and shape, query coverage/order, result validity, and
clean process termination are also checked.

### Integrity Checks and Final Reward

The normalized quality reward is accepted only after runtime and validity gates
and the independent trajectory audit pass. Failure at any gate produces zero.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Prepare the GPU runtime and configure the independent integrity judge. Download
as a host user distinct from submission UID 10001, following the asset guide,
so the reference model's private file permissions retain their intended effect.

```bash
python scripts/download_assets.py --task task-2-3
bash scripts/run_task.sh --task task-2-3 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-2-3/`.
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
| [Starter notes](environment/starter/README.md) | Teacher-side baseline and public validation |
| [Resource policy](environment/docs/available_resources.md) | Development access and offline submission rules |
