# Memory-constrained Dense Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `memory-constrained-dense-retrieval` |
| Version | 1.0.0 |
| Authors | Search-SWE |
| Primary metric | Accuracy@3 |
| Compute | 16 CPUs; 0.5 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 7200 s |
| Dataset | NaturalQuestions |
| Hidden queries | 20 |

Search a fixed vector collection larger than available RAM while meeting strict query deadlines.

### Overview

This task contains 1.5 million precomputed NaturalQuestions document vectors,
each with 1,024 float32 dimensions. The raw vectors occupy about 6.14 GB,
while the runtime has only 512 MiB of memory.

The challenge is to design an index, storage layout, and query path that work
together under that mismatch. Retrieval quality alone is insufficient:
the system must become ready quickly and serve independent query invocations
within a tight end-to-end deadline. The architecture is open, so memory
management and service lifecycle are as important as the search algorithm.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/vectors.f32` | The fixed document-vector collection |
| `data/metadata.jsonl` and `data/vector_config.json` | Document mapping and vector layout |
| `data/validation/` | 20 public examples, query vectors, metadata, and labels |

Files are restored under the task's `data/` and mounted at `/task/data`.
The hidden workload contains 20 queries, disjoint from public validation.
Every hidden query is scored for both retrieval correctness and latency.

The asset manifest fixes the packaged revision and each file's size and SHA-256.
Its [source record](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/SOURCES.md)
identifies BGE-large-en-v1.5 with L2 normalization, but does not record the
original encoder revision. These are preserved frozen vectors, not a newly
reconstructed embedding dataset. Original source attribution and terms apply;
the collection does not grant a blanket license for all underlying materials.

Document and query IDs are independent opaque random identifiers. Corpus
vector rows and metadata are shuffled together, with vector values preserved
bit for bit and relevance labels mapped consistently. Labels remain original
NQ relevance judgments. Both splits were selected from full-corpus exact
Top-3 hits, favoring small relevant-document margins over rank four and
balancing those margins between splits. This margin is a difficulty proxy,
not evidence of failure by a measured ANN baseline.

#### Fixed Components and Allowed Changes

Document and query vectors are supplied inputs. Index organization, compression,
storage access, and the retrieval implementation may change. External models,
retrieval services, and answer mappings are not part of the task.
An internal representation must still produce valid results for the supplied
vectors and preserve their document identities.

#### Environment and Resource Limits

Both phase containers provide 16 CPUs for development and offline construction, 512 MiB aggregate memory, no swap, 100 GiB storage allowance and no GPU. Final online queries have a separate one-logical-CPU budget: the client, restarted service and every descendant share the same single allowed CPU. Both phases use a per-process open-file soft and hard limit of 1,048,576, including non-root verifier build and query processes. The memory cgroup includes the build, resident service, clients, all descendants, charged file-cache pages, and runtime/verifier overhead; it is not a per-process allowance. Both agent development and final verification have a 120-minute total limit. Failed development experiments do not by themselves set the final reward; final verification starts in a fresh container. The final build has a 150-second limit and each query has a 0.5-second hard deadline. The 100 GiB storage allowance is an audited policy, not a kernel filesystem quota; index sizes are reported.

For representative query tests, first terminate only your own build-started search service, then run `/usr/local/bin/search-swe-query-cpu /app/run.sh` with the normal query arguments. The identical protected launcher is provided in both images and used automatically by the verifier for every query. It selects the first CPU in the permitted affinity mask, pins execution there and prevents later affinity expansion across threads, forks and execs. It configures OpenMP with `KMP_AFFINITY=disabled` and `OMP_PROC_BIND=false`, and clears `GOMP_CPU_AFFINITY`, so numerical runtimes keep the inherited mask. Do not re-enable runtime affinity changes. Submitted query executables must use the image's native 64-bit architecture. Build-time services are terminated before this boundary; a development service left running with the build's wider CPU access would give an unrepresentative measurement. Launcher startup is included in the existing query deadline and latency measurement. The CPU is not reserved exclusively, and the verifier does not change the host scheduler or flush caches.

The supplied index workspace is `/task/index`, a fresh 64 MiB (67,108,864-byte) tmpfs mounted in both phases. Use it as `--index-dir` for representative development tests and final execution. All final build and query artifacts, including indexes, document lookup tables, executables, logs, temporary files and caches, must fit there throughout the final build and query workload; the kernel rejects writes beyond its capacity. The requested result JSONL file is the exception and must be written to the supplied `--output` path. Sparse files also count by logical size for the grader limit. This workspace is charged to the same 512 MiB memory cgroup, not an additional memory allowance. Keep submitted source files and development scratch files under `/app` within the general storage allowance. The timed final build must derive corpus-dependent search state from the supplied inputs; it must not reuse prebuilt corpus indexes or learned search tables bundled with the source. Do not place generated search state elsewhere or use other persistent writable paths or query-output directories to evade the workspace budget. Anonymous memory and IPC shared memory are permitted within the total memory budget, but POSIX shared-memory files and submission-owned System V IPC objects are removed and checked during the post-build restart and cannot preserve an index across it. The supplied corpus remains read-only and may be read for genuine retrieval and reranking.

The submitted build must finish within **150 seconds**, including service
startup. Every query invocation has a **0.5-second wall-clock limit**, measured
from process start through exit and protected output capture, including the full query path. The grader records index size.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Designing dense-vector search under a memory budget smaller than the corpus.
- Balancing index preparation, retrieval quality, and query latency.
- Keeping a reusable service available across short-lived query clients.
- Accounting for process startup and serialization in end-to-end performance.

## Verification Explanation

### Submission Contract

The deliverable contains `/app/build.sh` and `/app/run.sh`. The first builds the
index and starts a reusable service; the second accepts query-vector files and
returns exactly three ranked document IDs with scores per query.

The verifier supplies file and index paths and may invoke the query entry point
separately for each question. Submission execution is unprivileged, with
persistent and runtime artifacts written to the supplied index directory.
The complete interface is in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Each query earns 1 only when its invocation exits successfully, its valid output
is captured within 0.5 seconds, and its top three results contain a relevant
document. Otherwise that query earns 0. The primary metric is the mean of
these 20 binary scores; 17 passing queries give Accuracy@3 = 0.85 and fail the minimum 0.95 quality requirement. The report
also records retrieval accuracy without the latency gate for diagnosis.

#### Correctness and Resource Gates

The verifier checks output coverage, document IDs, finite scores, ordering,
and the execution deadline for each invocation. Incorrect answers, malformed
outputs, failed invocations, and timeouts reduce the corresponding query score;
the remaining queries still run, and the aggregate quality floor still applies. A query timeout terminates its invocation
process group while preserving the separately started query service. Build
failure, an invalid index, or invalid evaluator inputs still invalidate the
evaluation. The 512 MiB container memory limit applies throughout execution.

#### Integrity Checks and Final Reward

A trajectory audit independently checks task compliance. Let `A` be the mean of the 20 latency-gated Accuracy@3 values and `L95` the P95 duration in seconds. The service must achieve `A >= 0.95`: at least 19 of the 20 queries must pass the accuracy, output and 0.5-second execution gates. Below this quality floor the reward is zero. At or above it, the normalized reward before the integrity gate is `A * min(1, 0.030 / L95)`; the displayed score is 100 times this reward. Accuracy and the latency factor are still reported when the quality floor is missed. This is an acceptance threshold on this fixed workload, not a statistical confidence guarantee. At `A=1`, P95 values of 30, 60 and 150 ms earn 100, 50 and 20 points. At `A=0.95`, 30 and 150 ms earn 95 and 19 points; `A=0.90` earns zero regardless of speed. A failed build, invalid or oversized index, invalid evaluator inputs, out-of-memory kill observed in the final verifier container, or failed retrieval-integrity check makes the overall reward zero.

The verifier starts from an empty index workspace and builds once. After the successful build, it terminates all submission processes while preserving the workspace and clearing POSIX shared-memory files and submission-owned System V shared memory, message queues and semaphores, to verify that the stored index can be deployed independently. The first run.sh call must automatically load that stored state and start its service if needed; this cold startup is included in that call's 0.5-second deadline and latency. Later calls may reuse the service for one sequential pass over 20 distinct hidden queries in fixed stored order. There is no hidden-query warmup or repeated hidden-query round. The verifier does not flush the operating-system file cache; file pages and index state created during the build may remain cached. P95 is the nearest-rank quantile: sort all 20 end-to-end durations and take the 19th (one-based, `ceil(0.95 * 20)`). Timeouts and failed launches contribute 0.5 seconds; all other invocations, including nonzero exits and invalid outputs, contribute their externally measured duration capped at 0.5 seconds. Timing uses a monotonic clock and Linux process-exit events. Build time ends at observed process exit. Query time runs from immediately before process creation until the verifier has captured the bounded output into protected storage after client exit; input reading, communication, retrieval, result output, exit and output capture are included. Both P95 and the 0.5-second query deadline use this capture-inclusive duration. Process-exit and output-capture durations are also reported separately. The verifier does not wait for late results: it attempts capture immediately after observing exit, and capture failure or completion after the deadline earns no query credit. Timeout termination and cleanup are recorded separately and do not inflate completed-query latency. A timed-out client is terminated while a separately started query service remains available for subsequent queries. Nonpositive or nonfinite timings invalidate evaluation. Independent author reruns start a fresh build and service; they measure stability and do not increase the count of distinct queries.

It uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 and receives its
DeepSeek endpoint and key only in the verifier.

### Running This Task

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
bash scripts/run_task.sh --task memory-constrained-dense-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/memory-constrained-dense-retrieval/`.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
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

### Local regression checks

Run `python -m unittest discover -s tasks/memory-constrained-dense-retrieval/tests -p "test_*.py"`. Runtime grading requires Linux blocking process waits and a cgroup-v2 container with memory.max=536870912 and memory.swap.max=0. The grader records final-verifier container memory peak/events; any OOM kill in that container fails the evaluation. The two Compose overlays set identical 16-CPU, 512-MiB/no-swap container limits. The native query launcher enforces one logical CPU for all online submission processes.

The verifier snapshots each output immediately after observing client exit, in a root-only directory. Query timing ends after capture completes, so every scored byte was received within the measured interval. Validation uses only that protected snapshot; writes through retained descriptors after capture cannot change it. The same capture-inclusive duration controls the 0.5-second deadline and P95.

## References

None.
