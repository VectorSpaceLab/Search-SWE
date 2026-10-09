# Memory-constrained Dense Retrieval

Search a fixed vector collection larger than available RAM while meeting strict query deadlines.

**Task:** `memory-constrained-dense-retrieval` · **Metric:** Mean per-query Accuracy@3 with a latency gate

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
| `data/validation/` | 20 public examples, query vectors, metadata, and labels |

Files are restored under the task's `data/` and mounted at `/task/data`.
The hidden workload contains 20 queries, disjoint from public validation.
Every hidden query is scored for both retrieval correctness and latency.

Document and query IDs are independent opaque random identifiers. Corpus
vector rows and metadata are shuffled together, with vector values preserved
bit for bit and relevance labels mapped consistently. Labels remain original
NQ relevance judgments. Both splits were selected from full-corpus exact
Top-3 hits, favoring small relevant-document margins over rank four and
balancing those margins between splits. This margin is a difficulty proxy,
not evidence of failure by a measured ANN baseline.

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

Each query earns 1 only when its invocation exits successfully within
0.5 seconds, its output is valid, and its top three results contain a relevant
document. Otherwise that query earns 0. The primary metric is the mean of
these 20 binary scores; 17 passing queries give Accuracy@3 = 0.85. The report
also records retrieval accuracy without the latency gate for diagnosis.

### Correctness and Resource Gates

The verifier checks output coverage, document IDs, finite scores, ordering,
and the execution deadline for each invocation. Incorrect answers, malformed
outputs, failed invocations, and timeouts affect only the corresponding query;
the remaining queries still run. A query timeout terminates its invocation
process group while preserving the service started during the build. Build
failure, an invalid index, or invalid evaluator inputs still invalidate the
evaluation. The 2 GiB container memory limit applies throughout execution.

### Integrity Checks and Final Reward

A trajectory audit independently checks task compliance. When evaluation is
valid and the audit passes, reward is the mean per-query score (`passed / 20`);
otherwise reward is `0`. The evaluation report displays `100 * (passed / 20)`
before the trajectory gate.
It uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 and receives its
DeepSeek endpoint and key only in the verifier.

## Running This Task

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the verifier's integrity-judge credentials using the evaluation guide.
The candidate search system uses supplied vectors and does not require
external model-service credentials.

```bash
python scripts/download_assets.py --task memory-constrained-dense-retrieval
bash scripts/run_task.sh --task memory-constrained-dense-retrieval --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/memory-constrained-dense-retrieval/`.
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
