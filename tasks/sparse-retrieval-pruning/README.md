# Sparse Retrieval Pruning

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `sparse-retrieval-pruning` |
| Version | 1.0.0 |
| Authors | Search-SWE |
| Primary metric | quality_gated_linear_starter_speedup |
| Compute | 1 CPUs; 32 GiB RAM; 80 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 16200 s |
| Dataset | MS MARCO Passage v1 with frozen SPLADE sparse vectors |
| Hidden queries | 1000 |

Optimize a sparse retrieval system while preserving strict quality requirements.

### Overview

Sparse retrieval efficiency depends on how terms, document identities, and
posting lists fit together. A compact index is not useful if remapped terms
point to the wrong postings, and aggressive pruning is not useful if it
removes relevant results.

The task packages one million MS MARCO documents as sets of opaque,
unweighted term IDs derived from frozen sparse representations. It evaluates
a Python implementation against the unpruned reference starter.
The goal is to preserve strong retrieval quality while reducing total query
wall time relative to that reference. Quality thresholds are hard gates;
passing submissions receive `clip((speedup - 4) / 12, 0, 1)`: 4× starts scoring,
10× earns 50 points and 16× earns 100 points.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | One million documents represented by opaque term sets |
| `data/validation/` | 200 public queries, qrels, statistics, and reference Top-100 results |
| `environment/starter/` | Unpruned retrieval starter |
| `environment/docs/index_format.md` | Starter dictionary, posting, and metadata layout |

The verifier has 1,000 hidden queries, relevance labels, and reference data,
isolated from the agent environment. It runs its own unpruned reference starter
when measuring the runtime baseline.

The public assets are pinned to an immutable dataset revision in
[assets.json](assets.json). Downloading verifies file sizes and SHA-256 checksums.
Their Hugging Face source paths are under `tasks/sparse-retrieval-pruning/`.

#### Fixed Components and Allowed Changes

The corpus, executable interface, and quality/runtime requirements are fixed.
The agent may replace the starter's index format or retrieval algorithm.
All indexing, scoring, pruning, and ranking logic must remain Python source;
thin Bash launch wrappers and normal use of preinstalled packages such as NumPy
are allowed.

The submission must be single-process and single-threaded. Native submission
code, compiled submission executables, and parallel query execution are outside
the task. The input is set-valued; readers should not assume that weighted
encoder outputs or a retrainable transformer are supplied.

#### Environment and Resource Limits

The CPU Python 3.12 environment has one CPU, 32 GiB memory, 80 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has 270 minutes (worst-case stage budget).
The current execution wrapper caps the candidate build at 3,600 seconds and
each query run at 900 seconds; the starter build is capped at 1,800 seconds. The starter-relative latency reward is measured
within those bounds, and all verification stages share the overall phase budget.

The formal build/search path requires no external service, credentials, or
downloads. The private integrity judge's API access is a separate concern.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Building a bounded-memory inverted index over a large sparse corpus.
- Keeping dictionaries, document mappings, and posting metadata consistent.
- Reducing retrieval work without sacrificing required ranking quality.
- Achieving speedups through Python data structures and algorithms rather than parallelism.

## Verification Explanation

### Submission Contract

The transferred system includes `/app/build.sh` and `/app/run.sh`. The build
creates all persistent state under the caller's index directory; the query
entry point returns the required ranked Top-100 corpus documents.
The verifier runs submission commands unprivileged with the submission tree
read-only.

The exact fields and CLI are in [instruction.md](instruction.md). The
[index format guide](environment/docs/index_format.md) explains the starter,
but that particular storage format is not a required output artifact.

### Evaluation

#### Search Quality

Quality is measured using mean NDCG@10 and qrels-based Recall@100. The current
minimums are **0.89** and **0.99** respectively.

#### Correctness and Latency Reward

The fixed corpus contains 1,000,000 documents. Each formal search invocation
processes the same 1,000 hidden queries; the public development set contains
200 queries. The verifier runs five measurement rounds with fresh processes. Odd rounds run
starter then candidate; even rounds run candidate then starter. It uses the
median of each system's five complete search wall times and divides the starter
median by the candidate median. Timing includes process launch, Python imports,
index loading, reading all queries, retrieval, output writing and process exit.
There is no separate warmup and the OS file cache is retained between calls.
Each round uses a fresh private output directory and temporary HOME/TMPDIR; the
built index and submission source are read-only during search. Do not write to
the index, reuse answers across invocations, or rely on files from earlier runs.
All required persistent state must be built from public inputs. The verifier
isolates accessible paths and clears temporary state between invocations.
Every candidate round must meet both quality floors; reported aggregate quality
is the arithmetic mean across rounds. Outputs are validated in every round.
Both positive finite timing medians are required; failures yield zero reward.

The candidate build is limited to 3,600 seconds, the reference build to 1,800
seconds, and each complete search invocation to 900 seconds. The overall
verifier budget is 16,200 seconds, covering builds, ten searches and the
integrity judge. Both systems use the same one-CPU affinity, 32 GiB memory
limit, one-thread library settings and isolation. New threads are blocked;
Python worker processes are monitored and the trajectory is audited. Thin
serial shell launch wrappers remain allowed. This protocol does not grant
permission to run additional workers.

Let `s = median(starter wall time) / median(candidate wall time)`. If every
round meets both quality gates and all execution/output/integrity checks pass,
reward is `max(0, min(1, (s - 4) / 12))`, and score is 100 times reward.

#### Integrity Checks and Final Reward

If either quality threshold, output and execution checks, or the trajectory
audit fails, final reward is `0`. Otherwise the final reward is the speedup
reward described above. The verifier measures reference wall time afresh for each run.
The audit uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 with
verifier-only DeepSeek endpoint and key settings.

### Running This Task

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the verifier's integrity-judge credentials independently of the coding
agent. The submission itself does not need task-resource API keys or a model
download. The standard asset command restores the published corpus and
validation files directly.

```bash
python scripts/download_assets.py --task sparse-retrieval-pruning
bash scripts/run_task.sh --task sparse-retrieval-pruning --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/sparse-retrieval-pruning/`.
Replace `YOUR_AGENT_MODEL` with your configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

### Task Files

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

### Revision 0.5.2 validation

This revision implements the approved 4×–16× speedup calibration and five-round
alternating protocol. Linux x86_64 Landlock and seccomp are required by the
verifier (missing kernel support fails closed). Submission temporary writes
are confined to the current output and scratch directories; source and built
index are read-only in search. Metrics, hidden labels and prior round results
are inaccessible. Shell-wrapper subprocesses are permitted only for serial
launching; Python workers are sampled during execution and the existing judge
audits the full single-process policy. The single-thread policy is also enforced
by a kernel filter and library environment settings. The 80 GiB storage value
is a declared harness budget, not a kernel filesystem quota.

On verifier exit, build/search metrics, stdout/stderr and each round's result
file are retained under `verifier/runner-artifacts/` in the job. This diagnostic
copy runs after measurement and also preserves logs when a build/search fails.
Indexes and temporary scratch files are not exported.

Run task-local regression tests with
`python -m unittest discover -s tasks/sparse-retrieval-pruning/tests -p 'test_*.py'`.
Runtime evidence and full-score feasibility are recorded by the author in the
calibration delivery report; they are not established by static validation.

Revision 0.5.1 also unifies login-shell Python aliases with `/opt/conda` and
sets single-thread library defaults in both images. This repairs the 0.5.0
trial's environment mismatch; its incomplete run is not difficulty evidence.

Revision 0.5.2 removes a per-UID `RLIMIT_NPROC` that incorrectly counted
unrelated containers on the host and could block the starter's serial shell
launch. The container PID limit, kernel thread prohibition, worker monitoring,
quality gates and scoring are unchanged.

## References

None.
