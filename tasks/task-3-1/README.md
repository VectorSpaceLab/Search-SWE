# Sparse Retrieval Index Repair

Repair and accelerate a sparse retrieval system while preserving strict quality requirements.

**Task:** `task-3-1` · **Mode:** Repair · **Metric:** Binary quality and relative-runtime pass

## Overview

Sparse retrieval efficiency depends on how terms, document identities, and
posting lists fit together. A compact index is not useful if remapped terms
point to the wrong postings, and aggressive pruning is not useful if it
removes relevant results.

The current task packages one million MS MARCO documents as sets of opaque,
unweighted term IDs derived from frozen sparse representations. It evaluates
a Python implementation against a corrected, unpruned starter.
The goal is to preserve strong retrieval quality while reducing total query
wall time to at most 30% of that reference. This is the executable task's
current definition, rather than the earlier draft's collection of proposed
postings and latency targets.

## What This Task Tests

- Building a bounded-memory inverted index over a large sparse corpus.
- Keeping dictionaries, document mappings, and posting metadata consistent.
- Reducing retrieval work without sacrificing required ranking quality.
- Achieving speedups through Python data structures and algorithms rather than parallelism.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | One million documents represented by opaque term sets |
| `data/validation/` | 200 public queries, qrels, statistics, and reference Top-100 results |
| `environment/starter/` | Corrected retrieval starter |
| `environment/docs/index_format.md` | Starter dictionary, posting, and metadata layout |

The verifier has 1,000 hidden queries, relevance labels, and reference data,
isolated from the agent environment. It runs its own corrected starter when
measuring the runtime baseline.

The public assets now have an immutable dataset revision in [assets.json](assets.json).
The old README's pending-publication note no longer applies. Downloading uses
the same size and SHA-256 checks as other tasks.

### Fixed Components and Allowed Changes

The corpus, executable interface, and quality/runtime requirements are fixed.
The agent may replace the starter's index format or retrieval algorithm.
All indexing, scoring, pruning, and ranking logic must remain Python source;
thin Bash launch wrappers and normal use of preinstalled packages such as NumPy
are allowed.

The submission must be single-process and single-threaded. Native submission
code, compiled submission executables, and parallel query execution are outside
the task. The input is set-valued; readers should not assume that weighted
encoder outputs or a retrainable transformer are supplied.

### Environment and Resource Limits

The CPU Python 3.12 environment has one CPU, 32 GiB memory, 80 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has 80 minutes.
The current execution wrapper caps the candidate build at 3,600 seconds and
query run at 900 seconds. The relative-runtime gate still applies within
those bounds, and all verification stages share the overall phase budget.

The formal build/search path requires no external service, credentials, or
downloads. The private integrity judge's API access is a separate concern.

## Submission Contract

The transferred system includes `/app/build.sh` and `/app/run.sh`. The build
creates all persistent state under the caller's index directory; the query
entry point returns the required ranked Top-100 corpus documents.
The verifier runs submission commands unprivileged with the submission tree
read-only.

The exact fields and CLI are in [instruction.md](instruction.md). The
[index format guide](environment/docs/index_format.md) explains the starter,
but that particular storage format is not a required output artifact.

## Evaluation

### Search Quality

Quality is measured using mean NDCG@10 and qrels-based Recall@100. The current
minimums are **0.89** and **0.99** respectively.

### Correctness and Resource Gates

The verifier measures the candidate and corrected starter on the same workload
and resource allocation. Candidate query wall time must be no more than
**0.30 times starter query wall time**. Passing only quality or only runtime
is insufficient. Successful build/run, valid outputs, and implementation
restrictions also remain required.

### Integrity Checks and Final Reward

Final reward is `1` only if both quality thresholds, the runtime gate, output
and execution checks, and the trajectory audit pass. Any failure gives `0`.
The corrected starter is a measured runtime reference, not a fixed published
timing that submissions can assume on every machine.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the verifier's integrity-judge credentials independently of the coding
agent. The submission itself does not need task-resource API keys or a model
download. The standard asset command now restores the published corpus and
validation files directly.

```bash
python scripts/download_assets.py --task task-3-1
bash scripts/run_task.sh --task task-3-1 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-3-1/`.
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
| [Index format guide](environment/docs/index_format.md) | Starter layout and consistency relationships |
| [Resource policy](environment/docs/available_resources.md) | Python dependency and execution restrictions |
