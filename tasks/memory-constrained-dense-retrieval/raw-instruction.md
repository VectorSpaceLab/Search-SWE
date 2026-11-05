# Memory-constrained Dense Retrieval

## Task Description

Build an executable search system over the supplied vector corpus. Given a query vector, the system should retrieve and rank the most relevant corpus items.

The service must reach at least 95% latency-gated Accuracy@3. The objective is to meet this quality floor and maximize the quality-and-tail-latency reward on held-out queries under the evaluator's resource constraints. You may use any indexing, storage, and retrieval architecture that satisfies the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat the supplied data and documentation under `/task` as read-only; `/task/index` is the writable bounded index workspace.
- Use only the supplied precomputed vectors and task data for retrieval. Do not use external models, retrieval services, external datasets containing evaluation results, or precomputed query-to-result mappings.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- `build.sh` and `run.sh` must be executable files under `/app`.
- During verification, `/app` is read-only and the submission runs as a non-root user. Use the supplied `--index-dir` for persistent and runtime-generated artifacts; write query results to the separately supplied `--output` path.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.
- The `build.sh` process must complete within 150 seconds, including index construction and service startup.
- Each per-query `/app/run.sh` invocation must complete within 0.5 seconds of end-to-end wall-clock time, measured from process start through exit and protected output capture. The verifier may invoke `/app/run.sh` separately for each query.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --vectors /task/data/vectors.f32 \
  --metadata /task/data/metadata.jsonl \
  --config /task/data/vector_config.json \
  --index-dir /task/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. After the verifier terminates the build-started processes, `run.sh` must automatically restart from persisted index files on its first call and keep that query service available for later calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Do not require the verifier to know any additional fixed paths.

### Query interface

The verifier invokes:

```bash
/app/run.sh \
  --index-dir /task/index \
  --query-vectors /task/data/validation/query_vectors.f32 \
  --query-metadata /task/data/validation/query_metadata.jsonl \
  --query-config /task/data/validation/vector_config.json \
  --output /tmp/results.jsonl \
  --top-k 3
```

`run.sh` must process every supplied query and write exactly one result object for each input query. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

### Output contract

The complete output must be written before `run.sh` exits. After observing exit, the verifier immediately captures the output into protected storage; capture is included in query time, and writes after capture are ignored.

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- `results` must contain exactly three items when invoked with `--top-k 3`;
- every result must contain a `doc_id` identifying a document from the supplied corpus and a finite numeric `score`;
- document IDs must be unique within a query;
- results must be ordered from highest to lowest score; and
- equal-score results must use corpus order as the tie-break.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/vectors.f32` — 1,500,000 normalized float32 corpus vectors with dimension 1024.
- `/task/data/metadata.jsonl` — 1,500,000 metadata rows corresponding one-to-one with the corpus vectors.
- `/task/data/vector_config.json` — configuration for the corpus vector collection.
- `/task/data/validation/query_vectors.f32` — public development query vectors.
- `/task/data/validation/query_metadata.jsonl` — metadata corresponding to the public query vectors.
- `/task/data/validation/vector_config.json` — configuration for the public query vectors.
- `/task/data/validation/queries.jsonl` — public development query records.
- `/task/data/validation/ground_truth.jsonl` — normalized labels for the public queries.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files under `/app`.

```text
/app/
├── build.sh          # executable build and service-start entry point
├── run.sh            # executable query entry point
├── src/              # optional implementation modules
└── README.md         # optional implementation notes and self-test details
```

## Verification

After the Agent phase, the Harbor verifier runs the submission in the same task environment and uses the private test split. The verifier checks the following items:

1. **Retrieval integrity.** The submission must implement a genuine vector retrieval system over the supplied corpus vectors. It must not obtain relevance judgments or results through hidden labels, hard-coded query-to-document mappings, precomputed answer files, external datasets containing the evaluation judgments, or external retrieval services.
2. **Executable and runtime behavior.** The verifier checks that `build.sh` and `run.sh` exist and are executable. It invokes `build.sh` and requires it to complete successfully within 150 seconds, including index construction and service startup. It then invokes `run.sh` for the hidden query vectors and enforces the specified retrieval-latency limit.
3. **Output validity.** The verifier checks the JSONL result structure, query coverage, result count, duplicate handling, document IDs, scores, and ranking output for each query. A query with invalid output or a failed `run.sh` invocation receives zero credit; the verifier continues with the remaining queries.
4. **Final retrieval score.** Each query earns 1 only for a successful invocation with valid output captured within 0.5 seconds and a relevant document in Top-3; otherwise it earns 0. Let `A` be the mean of the 20 latency-gated Accuracy@3 values and `L95` the P95 duration in seconds, both from the round selected by median P95. The service must achieve `A >= 0.95`: at least 19 of the 20 queries must pass the accuracy, output and 0.5-second execution gates. Below this quality floor the reward is zero. At or above it, the normalized reward before the integrity gate is `A * min(1, 0.030 / L95)`; the displayed score is 100 times this reward. Accuracy and the latency factor are still reported when the quality floor is missed. This is an acceptance threshold on this fixed workload, not a statistical confidence guarantee. At `A=1`, P95 values of 30, 60 and 150 ms earn 100, 50 and 20 points. At `A=0.95`, 30 and 150 ms earn 95 and 19 points; `A=0.90` earns zero regardless of speed. A failed build, invalid or oversized index, invalid evaluator inputs, out-of-memory kill observed in the final verifier container, or failed retrieval-integrity check makes the overall reward zero.

### Timing and resource protocol

The verifier performs five independent measurement rounds. Each round starts from an empty index workspace and a fresh build, with previous submission processes, IPC state, query inputs and output directories cleared. After the successful build, it terminates all submission processes while preserving the workspace and clearing POSIX shared-memory files and submission-owned System V shared memory, message queues and semaphores, to verify that the stored index can be deployed independently. The first run.sh call must automatically load that stored state and start its service if needed; this cold startup is included in that call's 0.5-second deadline and latency. Later calls may reuse the service for one sequential pass over the same 20 distinct hidden queries in fixed stored order within each round. There is no query warmup. Query-result caches do not carry over between rounds. Each round produces its own Accuracy@3 and P95; sort rounds by P95, breaking ties by round order, and use the third round in that order for both the accuracy and latency terms of the final score. Do not pool the 100 measurements or select a round by accuracy. The verifier does not flush the operating-system file cache; file pages and index state created during the build may remain cached. P95 is the nearest-rank quantile: sort all 20 end-to-end durations and take the 19th (one-based, `ceil(0.95 * 20)`). Timeouts and failed launches contribute 0.5 seconds; all other invocations, including nonzero exits and invalid outputs, contribute their externally measured duration capped at 0.5 seconds. Timing uses a monotonic clock and Linux process-exit events. Build time ends at observed process exit. Query time runs from immediately before process creation until the verifier has captured the bounded output into protected storage after client exit; input reading, communication, retrieval, result output, exit and output capture are included. Both P95 and the 0.5-second query deadline use this capture-inclusive duration. Process-exit and output-capture durations are also reported separately. The verifier does not wait for late results: it attempts capture immediately after observing exit, and capture failure or completion after the deadline earns no query credit. Timeout termination and cleanup are recorded separately and do not inflate completed-query latency. A timed-out client is terminated while a separately started query service remains available for subsequent queries. Nonpositive or nonfinite timings invalidate evaluation. Independent author reruns start a fresh build and service; they measure stability and do not increase the count of distinct queries.

Both phase containers provide 16 CPUs for development and offline construction, 512 MiB aggregate memory, no swap, 100 GiB storage allowance and no GPU. Final online queries have a separate one-logical-CPU budget: the client, restarted service and every descendant share the same single allowed CPU. Both phases use a per-process open-file soft and hard limit of 1,048,576, including non-root verifier build and query processes. The memory cgroup includes the build, resident service, clients, all descendants, charged file-cache pages, and runtime/verifier overhead; it is not a per-process allowance. Both agent development and final verification have a 120-minute total limit. Failed development experiments do not by themselves set the final reward; final verification starts in a fresh container. The final build has a 150-second limit and each query has a 0.5-second hard deadline. The 100 GiB storage allowance is an audited policy, not a kernel filesystem quota; index sizes are reported.

For representative query tests, first terminate only your own build-started search service, then run `/usr/local/bin/search-swe-query-cpu /app/run.sh` with the normal query arguments. The identical protected launcher is provided in both images and used automatically by the verifier for every query. It selects the first CPU in the permitted affinity mask, pins execution there and prevents later affinity expansion across threads, forks and execs. It configures OpenMP with `KMP_AFFINITY=disabled` and `OMP_PROC_BIND=false`, and clears `GOMP_CPU_AFFINITY`, so numerical runtimes keep the inherited mask. Do not re-enable runtime affinity changes. Submitted query executables must use the image's native 64-bit architecture. Build-time services are terminated before this boundary; a development service left running with the build's wider CPU access would give an unrepresentative measurement. Launcher startup is included in the existing query deadline and latency measurement. The CPU is not reserved exclusively, and the verifier does not change the host scheduler or flush caches.

The supplied index workspace is `/task/index`, a fresh 64 MiB (67,108,864-byte) tmpfs mounted in both phases. Use it as `--index-dir` for representative development tests and final execution. All final build and query artifacts, including indexes, document lookup tables, executables, logs, temporary files and caches, must fit there throughout the final build and query workload; the kernel rejects writes beyond its capacity. The requested result JSONL file is the exception and must be written to the supplied `--output` path. Sparse files also count by logical size for the grader limit. This workspace is charged to the same 512 MiB memory cgroup, not an additional memory allowance. Keep submitted source files and development scratch files under `/app` within the general storage allowance. The timed final build must derive corpus-dependent search state from the supplied inputs; it must not reuse prebuilt corpus indexes or learned search tables bundled with the source. Do not place generated search state elsewhere or use other persistent writable paths or query-output directories to evade the workspace budget. Anonymous memory and IPC shared memory are permitted within the total memory budget, but POSIX shared-memory files and submission-owned System V IPC objects are removed and checked during the post-build restart and cannot preserve an index across it. The supplied corpus remains read-only and may be read for genuine retrieval and reranking.

## Hidden Test Overview

The hidden evaluation contains held-out query vectors with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.

These documents are part of the Agent-visible task data and should be treated as read-only.
