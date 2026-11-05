# Incremental Vector Search

## Task Description

Build a vector index for a collection receiving new vectors between searches.
Minimize the total number of missed exact neighbors subject to separate time gates. Any algorithm is allowed;
no embedding training or particular starter is required. Two datasets are run
independently: Qdrant DBpedia 1536 and 3072 dimensions. Use float32 vectors without
normalizing the canonical inputs. Ranking uses their original Euclidean L2.
Internal projections, quantization and compressed candidate indices are allowed.

## Requirements

Each dataset starts with 105,000 vectors, IDs 0 through 104999, in
`/task/data/corpus/<dimension>/initial.npy`. Ten batches of 1,000 additional vectors
receive consecutive IDs starting at 105000; each batch is followed immediately
by 1,000 disjoint held-out queries at K=100,200,400,800,1000, in that order.
The same query order is used for all K values. Both datasets have independent
indices and process lifetimes. Future insertions and queries are not available
before their events. Maintain the index incrementally; do not rebuild the full
index after every insertion batch. Use one index for all five K values.

### Build interface

Build request:
`{"op":"build","vectors":"/task/data/corpus/1536/initial.npy","dimension":1536,"count":105000,"threads":16,"state_dir":"/work/state"}`.
Reply `{"ok":true}` after building. Startup, imports, compilation and public
warmup are included in the build budget. Matrix files are C-order float32 NPY.
Rows map to consecutive IDs. Mutable files belong under the supplied state_dir.

### Insertion interface

Insertion request:
`{"op":"insert","vectors":"/work/events/insert.npy","count":1000,"first_id":105000,"threads":16}`.
Reply `{"ok":true}` once all rows are searchable. The next request may be a
query. Load or copy any required vector data before replying: the event file
is removed after acknowledgement. Repair and maintenance belong to insertion
time, and work continuing into queries consumes query time.

### Query and output contract

Search request: `{"op":"search","vector":[0.1,0.2],"k":100}` (the real vector
has the dataset dimension). Reply `{"ids":[12,35],"distances":[0.2,0.5]}`.
Return at most K IDs with paired finite nonnegative L2 distances; partial and
empty results are allowed. Missing hits remain misses. Duplicate or unknown IDs
never earn hits; invalid ID/distance entries earn none. A malformed response,
failed query or more than K results makes that query's recall zero. All queries
remain in the denominator. Loss of the persistent process or framing makes the
remaining protocol impossible and fails that dataset.

## Available Validation Data

`/task/data/validation/<dimension>/{initial,inserts,queries}.npy` is a smaller
workload derived solely from the initial corpus, with 10,000 initial vectors,
ten batches of 100 inserts and 100 queries, and the same K values. Development
queries are excluded from that workload's corpus and disjoint from hidden
queries. `ground_truth.npy` contains exact Top-1000 IDs in query-row order, and `ground_truth_distances.npy` contains their squared L2 distances. Use the first K columns and the exact reference to check responses. Read `/task/docs/environment.md` and `/task/docs/available_resources.md`.

The optional development-only `/task/tools/profile_public.py` checks full-size
latency across ten successive insertions and 1,000 distinct queries per stage/K.
It samples queries and duplicate insert rows only from the public initial matrix,
runs the submission as UID 10001, and pins every query thread to one calibrated
CPU. Its default diagnostic target reserves 10% below the tightest official
budget across all ten stages. It does not check retrieval quality or produce a
score, and public-probe timings do not guarantee hidden-query timings. Validate
capacity after successive insertions, since later query cost can differ from
the first batch. For example, run as root in the agent container:
`python /task/tools/profile_public.py --dimensions 3072 --output /app/profiles/check1 -- bash
/app/submission/run.sh`.
Use a fresh output directory outside `/app/submission`; the profiling tool and
its outputs are not transferred as solver dependencies. The official workload,
10% gates and scoring formula are unchanged.

## Expected Artifacts

Create `/app/submission/run.sh` and its implementation under `/app/submission`.
The verifier transfers that directory, executes `bash /app/submission/run.sh`,
and communicates with this persistent process using one JSON object per line
on stdin/stdout. Flush each response; diagnostics go to stderr. At most one
request is outstanding. The response limit is 128 KiB per line. Do not emit
unsolicited stdout. No other agent files, installed dependencies or processes
are transferred. Rebuild any needed executable from included source at startup
or include a compatible executable. Both phases have the same CPU base runtime.
The entry point/source must be readable and binaries executable by UID 10001.

## Verification

### Metrics and score

For each query, recall is the number of unique valid returned IDs in its exact
Top-K divided by K. Count actual missing neighbors for the primary score:
`C_d = sum_queries(K-h)`. Every requested neighbor has equal weight, so a
K=1000 query has ten times as many positions as a K=100 query. There are
`25000000 = 10*1000*(100+200+400+800+1000)` positions per collection, and
`micro_recall_d = 1-C_d/25000000`. Report the unweighted mean of all 50 cell
recalls separately as macro recall. Each query uses its own exact Top-K target.

The fixed public reference is `/task/reference/baseline_search.py`. Its
`baseline_micro_recall` and `baseline_missing_neighbors` are published in
`/task/platform/limits.json`. Its training uses only initial vectors and its
insertions extend the same index. It is an optional reference.

Score logarithmic reduction in actual missing neighbors. Calculate C_d directly
from integer hits, without rescaling by K or introducing synthetic error units.
The dataset value is `G_d = clip(1-log(1+C_d)/log(1+C_base,d), 0, 1)`.
Matching or underperforming the public baseline earns zero; perfect retrieval
earns one if all resource/time gates pass. The score measures orders of
magnitude of error reduction, so improvements near perfect recall remain useful.
Failing a median build/insertion/query time gate, memory/storage violation or invalid execution gives that dataset zero regardless of quality. Individual timing timeouts are retained as infinite samples in the five-replay aggregation below.
The displayed score is `50 * (G_1536 + G_3072)`; Harbor reward is half that
sum in [0,1]. Faster-than-budget results earn no extra points. Raw Recall@K,
complete-query rates, error counts, timings and resources are reported separately.
The exact scan defines time limits; the public reference defines the quality anchor.

A separate trajectory/code audit checks incremental operation and integrity.
Do not access hidden data, exploit event visibility, manipulate grading or
resource accounting, hard-code benchmark answers, or use external answers.
A proven violation makes the whole task score zero. A missing/failed audit is
an infrastructure failure, not a measured quality result. Ordinary development
on public examples and legitimate caches within timed phases are allowed.

Exact L2 targets use the prepared platform's Faiss direct float32 distance kernel. When the
Kth distance has a tie, any otherwise valid ID at exactly that distance may earn
a hit. The verifier recomputes such distances; submitted distances cannot prove
a boundary tie. No numerical tolerance expands the true neighbor set.

### Timing and resource protocol

16 CPU cores, 32 GiB total container memory, 32 GiB storage.
No GPU is provided, and the submitted program cannot use external model
services or network APIs.
Development has 120 minutes. Build and
insert may use all 16 allocated CPUs. Queries are single-threaded, concurrency
one, including background maintenance. The controller restricts the complete
submission process tree to one CPU during queries; do not use parallel query
workers. Idle library thread pools are permitted. The process runs as UID 10001,
with no network and read-only runtime/input/submission files. Only state_dir is
writable. Processes/threads inherit isolation and resource limits.

The public `/task/platform/limits.json` contains build/insert hard limits and
the frozen exact full-scan times for every dataset, stage and K. Each query cell
must finish within 0.10 times its own reference time. No time can be transferred
between cells. Timing includes request delivery, candidate retrieval, distance
calculation, result selection, cache computation and output. It covers the entire
1,000-query cell. Only trusted scoring pauses are excluded; the submission is
stopped during those pauses. Use `/task/reference/exact_search.py` as the public
full-scan protocol example; it is not intended to meet the 10% gate.
Published calibration seconds are absolute for this run; a slower local exact
measurement cannot increase them. Inspect all ten stage-specific budgets.
Both phases use a legal 16-CPU allocation on the prepared platform. The profiler selects the current allocation and uses one CPU for queries.
Warmup uses only `/task/data/corpus/<dimension>/warmup.npy`, once before insertions.
Do not precompute held-out query results outside measured query phases.

No particular CPU model or fixed CPU IDs are required. The supplied images and isolation support Linux x86_64 with Landlock ABI >= 1 and seccomp; the image's Faiss build must support the host ISA. The organizer
measures the fixed exact reference in the same evaluation environment as the
submission, under identical CPU, query-order and warmup conditions. Locally
measured query budgets are frozen before the coding-agent trial. Moving the
evaluation to a different environment requires new reference measurements;
wall-clock budgets must not be copied between different machines.

## Hidden Test Overview

Future insertion batches and held-out query vectors are unavailable until their protocol events.
Development inputs come only from the initial corpus. Each dataset uses ten insertion/query stages
and its own index/process lifetime.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, optional public tools.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.


## Platform preparation and repeated timing

The evaluation launcher automatically runs trusted `tools/prepare_task.py` before coding-agent work. It verifies the finished inputs and public permissions, restores machine-local exact targets, measures one complete exact-reference replay and one public-baseline replay per collection when no valid cache exists, and freezes the measured reference durations and baseline error counts. Only formal submission verification uses five replays and timing medians. Fixed inputs, including hidden fixtures under `tests/data/`, are restored through `assets.json`; public validation is under `data/validation/`. Only public limits/validation are mounted into the agent. Cached outputs are checked by hash and reused for the same hardware, allocation, runtime, inputs and grading/reference code. A reboot alone does not invalidate them. Each evaluation uses one immutable cache directory for both phases. CPU IDs are selected from the current legal allocation, and preparation occurs outside the agent's time budget.

The verifier evaluates each collection through five independent replays, rebuilding from the original initial corpus each time and retaining the full incremental sequence within each replay. Build and insertion times are gated by their five-sample medians. Each query cell uses its own median wall time and the retrieval outputs from the corresponding median-time replay. Missing timings after a timeout count as positive infinity and never shrink the five-sample denominator. Invalid execution or resource violations in any replay invalidate that collection. Empty or malformed but correctly framed query responses retain zero recall as before. There is no reuse of submission state between replays.

The verifier phase allows 86,400 seconds: a primary wrapper of 80,000 seconds, a 3,600-second audit wrapper, and setup/finalization margin. Platform preparation rejects configurations whose declared five-replay workload exceeds the primary envelope. Repetition, calibration and audit implementation details are maintained here and in README.md, outside the agent-facing instruction.
