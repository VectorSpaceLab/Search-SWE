# Memory-constrained Dense Retrieval

Search a fixed vector collection larger than available RAM while meeting strict query deadlines.

**Task:** `task-1-2` · **Mode:** Implementation · **Metric:** Accuracy@3 with quality and performance gates

## Overview

This task contains 1.5 million precomputed NaturalQuestions document vectors,
each with 1,024 float32 dimensions. The raw vectors occupy about 6.14 GB,
while the runtime has only 2 GiB of memory.

The challenge is to design an index, storage layout, and query path that work
together under that mismatch. Retrieval quality alone is insufficient:
the system must become ready quickly and serve independent query invocations
within a tight end-to-end deadline. The architecture is open, so memory
management and service lifecycle are as important as the search algorithm.

## What This Task Tests

- Designing dense-vector search under a memory budget smaller than the corpus.
- Balancing index preparation, retrieval quality, and query latency.
- Keeping a reusable service available across short-lived query clients.
- Accounting for process startup and serialization in end-to-end performance.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/vectors.f32` | The fixed document-vector collection |
| `data/metadata.jsonl` and `data/vector_config.json` | Document mapping and vector layout |
| `data/validation/` | Five public examples, query vectors, metadata, and labels |

Files are restored under the task's `data/` and mounted at `/task/data`.
The hidden workload comprises five quality sentinels and 50 additional
performance queries. These serve different purposes: the primary quality
metric is not averaged over all 55.

### Fixed Components and Allowed Changes

Document and query vectors are supplied inputs. Index organization, compression,
storage access, and the retrieval implementation may change. External models,
retrieval services, and answer mappings are not part of the task.
An internal representation must still produce valid results for the supplied
vectors and preserve their document identities.

### Environment and Resource Limits

The CPU Python 3.12 runtime has 16 CPUs, 2 GiB memory, 100 GiB storage, and no
GPU. Both the agent phase and the Harbor verifier phase have two-hour budgets.

The submitted build must finish within **120 seconds**, including service
startup. Every query invocation has a **0.5-second wall-clock limit**, measured
from process start to exit, not just around the search kernel. The storage
budget constrains persistent artifacts; the grader also records index size.

## Submission Contract

The deliverable contains `/app/build.sh` and `/app/run.sh`. The first builds the
index and starts a reusable service; the second accepts query-vector files and
returns exactly three ranked document IDs with scores per query.

The verifier supplies file and index paths and may invoke the query entry point
separately for each question. Submission execution is unprivileged, with
persistent and runtime artifacts written to the supplied index directory.
The complete interface is in [instruction.md](instruction.md).

## Evaluation

### Search Quality

Every hidden quality sentinel must retrieve a relevant document in the top
three. Accuracy@3 below 1.0 fails this gate. MRR is diagnostic rather than a
separate reward component.

### Correctness and Resource Gates

The verifier checks the build and each query invocation, including the additional
50-query performance workload. Output coverage, document IDs, finite scores,
ordering, memory, and execution limits remain mandatory. A fast but incorrect
system and a correct but over-budget system both fail.

### Integrity Checks and Final Reward

A trajectory audit independently checks task compliance. Reward is `1` only
when quality, execution, output validity, and the audit all pass; otherwise `0`.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the verifier's integrity-judge credentials using the launcher guide.
The candidate search system uses supplied vectors and does not require
external model-service credentials.

```bash
python scripts/download_assets.py --task task-1-2
bash scripts/run_task.sh --task task-1-2 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-1-2/`.
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
