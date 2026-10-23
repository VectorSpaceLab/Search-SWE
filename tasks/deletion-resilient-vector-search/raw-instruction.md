# Deletion-resilient Vector Search

## Task Description

Implement a local graph index for a vector collection that repeatedly loses entries.
Preserve Top-10 nearest-neighbor recall while keeping queries fast and reclaiming
physical memory. Use any graph construction, search, compression, local repair,
compaction, or tombstone strategy. SPatch is not required. No training is required.
Do not rebuild the entire live graph after every deletion batch.

## Requirements

- `/task/data/public/{sift,gist}/base.f32`: one million little-endian float32 rows,
  dimension 128 for SIFT and 960 for GIST. Original zero-based row number is the
  immutable vector ID. Distance is squared Euclidean L2, without normalization.
- Each dataset's `config.json` declares dimensions/counts, `calibration.f32` holds
  10 public example/calibration queries, and `deletions.i32` contains an independent public
  development deletion permutation (100 blocks of 8000 little-endian int32 IDs).
- Public queries are the first ten official learn vectors, provided to illustrate
  the task/protocol rather than estimate hidden performance. Hidden evaluation uses a fixed
  5000-query sample from official SIFT query vectors and all 1000 GIST query vectors.
  The hidden deletion order differs from the public order. Both are fixed in advance.
- Each dataset is evaluated with a fresh process/index. Build on all one million
  vectors, run public calibration queries, then perform 100 delete/query stages.
  A stage removes 8000 currently live IDs and immediately runs the complete same
  hidden query set, in the same order. The final live population is 200000.
- Only the next deletion block is supplied. Hidden queries first arrive during
  the timed query part of stage 1. No hidden queries, answers or future deletion
  lists are provided at build time. Ground truth is exact L2 Top-10 over the full
  current live population, not a filtered initial Top-10.

### Build interface

A build request is
`{"op":"build","vectors":"/task/data/public/sift/base.f32","rows":1000000,"dimension":128,"work_dir":"/work/sift","calibration":"/task/data/public/sift/calibration.f32"}`.
The GIST build uses its own paths and dimension 960. Return `{"ok":true}` only after
construction is complete. The actual paths provided in the request are authoritative.

### Delete interface

A delete request is `{"op":"delete","stage":1,"ids":[12,34]}` with an actual array
of exactly 8000 IDs. Return `{"ok":true,"edge_count":123}` when deletion and repair
are complete. `edge_count` is an optional nonnegative count of stored directed graph
edges, including tombstones if stored; use null or omit it if unavailable. It is
reported as a self-reported diagnostic, never trusted for the memory score.

### Query and output contract

A query request is `{"op":"query","query_id":0,"vector":[0.0,1.0]}` with an actual
vector of the dataset dimension. Return
`{"query_id":0,"results":[{"id":12,"distance":0.25}],"distance_computations":123}`.
Echo the integer query ID and return at most 10 result objects. IDs must be integers;
distances must be finite nonnegative numbers, expressed as squared L2 distances.
`distance_computations` is an optional nonnegative count of query-to-vector distance
evaluations; null/omission means unavailable, not zero. Invalid or absent edge/distance
diagnostic counters are reported as unavailable and do not change recall. Recall is set-based; result
order and reported counters do not alter the score. The exact reference's float32
Top-10 IDs define ties. A malformed response, wrong query ID, non-integer ID, nonfinite/negative distance,
or more than 10 results earns that query zero. Unknown/deleted/duplicate IDs earn
no hit and are not replaced. An empty list or explicit failed query earns zero.
The process must continue serving subsequent requests. Failure to finish the full
100-stage workload invalidates that dataset.

## Available Validation Data

Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. The installed
`/task/tools/reference_server.py --kind full` is the exact scan reference, and
`--kind hnsw` is the fixed tombstone graph reference. They demonstrate the protocol;
using them is optional and full scanning alone fails the speed/graph requirements.
Run `/opt/conda/bin/python /task/tools/check_submission.py --run /app/run.sh --dataset sift`
(and `--dataset gist`) for a small full-corpus, ten-query, three-stage public check.
It reports recall and elapsed time against exact current-live-set answers, without
certifying all final resource limits. It creates a temporary directory under `/app`.
Only use public task data for tuning; do not seek hidden inputs or prior answers.

## Expected Artifacts

Create executable `/app/run.sh` and any required source/runtime files under `/app`.
Only `/app` is transferred. Do not submit prebuilt corpus-dependent indexes or caches;
construct them in the measured build operation. No symlinks in submitted artifacts.
The verifier launches `/app/run.sh` without arguments as UID 10001, with `/app`
read-only and its own empty working directory. The only writable submission location
is the `work_dir` sent in the build message. Use absolute paths and write temporary
files, compilers' outputs, libraries and caches there. Stdout is exclusively one
JSON response line per request, immediately flushed; stderr is for diagnostics.
The process stays alive for the entire dataset. Maximum response line size is 1 MiB.

## Verification

### Metrics and score

For each dataset, R is mean Recall@10 over all queries and then all 100 stages,
including failed queries as zero in the fixed denominator. The frozen public HNSW
reference uses FAISS 1.15.0, float32, M=32, efConstruction=40, efSearch=128. B0 is its
full-corpus query RSS, and Blive,t is its independently rebuilt live-set query RSS
at each stage, measured using the same runtime procedure. This independent rebuild
at every stage is an author-side reference procedure, not a permitted submission
strategy. These 101 values are fixed in
`/task/tools/runtime_limits.py`, independent of the submitted implementation.

Let Bmean be the mean of the 100 Blive,t values, and Mmean be the mean of the 100 Mt
values. E = clip((B0 - Mmean) / (B0 - Bmean), 0, 1). The reference denominator must
be positive and more than ten times the measured memory noise (and 1 MiB).
Recall credit measures improvement over a frozen tombstone HNSW baseline, not raw
recall. Its mean Recall@10 is Rbase=0.988931 for SIFT and Rbase=0.886659 for GIST,
published as `recall_baseline.recall` in each `/task/tools/runtime_limits.py`. It is the supplied
`/task/tools/reference_server.py --kind hnsw`, with the same FAISS settings above,
deletion/query workload and resource gates. The constants are frozen measurements;
parallel graph construction may cause small variation on reruns. Define
N = 100 * test_query_count * 10, C = N * (1 - R), and Cbase = N * (1 - Rbase).
N counts true-neighbor positions and C/Cbase count missed hits. The evaluator
rounds reconstructed counts to remove floating-point averaging noise; Cbase must
be at least one, or the reference is a setup error. Define
G = clip(1 - log(1 + C) / log(1 + Cbase), 0, 1), using the same log base.
This measures normalized reduction in log remaining errors. Adding one handles
zero errors at one-hit resolution, without a fitted exponent or target model score.
Each order-of-magnitude error reduction earns comparable additional credit;
matching/falling below baseline earns zero recall credit and zero errors earns full
recall credit. Rbase must be finite and in [0,1); missing/unfrozen/degenerate baselines
are evaluator setup errors, as is a missing/nonpositive/noninteger test query count.
The baseline has G=0 and earns zero, regardless of E. Memory savings earn credit
only in proportion to retrieval improvement: the recall contribution is 80*G,
and the memory bonus is 20*G*E. Full marks require
R=1 and E=1. Raw R, Rbase, C, Cbase, G and E are all reported.
The dataset score is 100 * G * (0.8 + 0.2 * E); final score is the equal mean of the
two dataset scores, in [0,100]. The harness reward is score/100. Inflating your M0
cannot improve E. Reclaimed bytes M0-M100 and fraction (M0-M100)/M0 are reported
as signed values. Also report all stage times, speedups, RSS, deletion time totals,
and available self-reported edge/distance counts. An integrity audit checks source
and trajectory for a full rebuild after every batch, forbidden query work in deletion, outside answer
acquisition and verifier/resource manipulation; clear violations make the whole
submission zero. Low recall or poor memory reclamation alone is not a violation.

### Timing and resource protocol

- Development: 120 minutes, 16 logical CPU cores, 32 GiB memory, 100 GiB task storage.
  No GPU, internet, external datasets, external models, or submission model API.
  The coding agent's own provider connection is not a submission resource.
  Development runs as unprivileged `submission`; `/app`, `/tmp` and the user home
  share a bounded filesystem. Harness logs cannot store task data.
- Evaluation: 16 logical CPUs for build/delete, one logical CPU and one in-flight
  request for querying. Idle helper threads may exist, but all query computation
  and subprocesses execute on the same CPU; do not override the verifier's affinity.
  BLAS/OpenMP defaults are one thread; build/delete may explicitly request up to 16.
- The public `REFERENCES` table in `/task/tools/runtime_limits.py` defines
  `build_timeout_seconds`, `delete_timeout_seconds`, `calibration_timeout_seconds`,
  and 100 measured `full_scan_seconds`. Build includes process startup, imports,
  compilation and indexing. Deletion includes all graph repair and compaction.
- For every stage t separately, query wall time must be <=
  `0.2 * full_scan_seconds[t-1]`. This covers sequential request delivery, parsing,
  all query/cached-result work, response generation and complete process-family
  suspension. No averaging time across stages. The exact reference uses the same
  protocol, float32 input and single-CPU policy. The submission uses the ten public examples for its initial memory measurement.
  Fixed timing and memory references are independent of that submission measurement.
- Previous query vectors/results may be cached. Stage 1 must pay its first retrieval
  and cache construction cost within its own budget. All test-query-dependent cache
  refresh, filtering, distances and output generation must occur in query requests.
  During deletion, only query-independent graph/index/cache maintenance is allowed.
  Work delayed into querying is charged there. Processes are stopped between phases.
- Memory covers the process family, vectors, graph, caches and temporary build/delete
  state. The Docker memory cap is 32 GiB, with swap disabled. Sampled total process-family RSS, including
  file-backed mappings and each process's resident shared mappings, is measured at
  phase boundaries and at least every 10 ms while awaiting responses. Peak sampled
  RSS during public calibration defines M0; each hidden query phase defines Mt.
  Allocator-retained physical pages still count. Build/delete peaks are also reported.
- Storage covers supplied vectors, submission files, work files, caches and diagnostics;
  the verifier checks regular-file logical/allocated sizes at boundaries and every
  0.5 seconds. A bounded ext4 filesystem also returns actual out-of-space errors:
  100 GiB minus fixed public inputs/submission files and a 512 MiB diagnostic
  reserve, including filesystem metadata. Each collection retains up to 128 MiB
  stderr, then drains/discards further diagnostics. Files must stay inside work_dir.
  There is a 512-process/thread cap.
  Submitted code receives no credentials or Internet socket access; local Unix-domain
  IPC is allowed. It cannot access
  protected grader files, hidden inputs, trajectory, reward files, or accounting.
- A build/delete failure or timeout, any stage query timeout, memory/storage excess,
  invalid memory measurement or incomplete dataset run gives that dataset zero,
  including its memory component. Missing/unfrozen reference assets are an evaluator
  setup error, never evidence of a solver failure or a positive memory score.

## Hidden Test Overview

Hidden evaluation uses 5,000 SIFT queries and 1,000 GIST queries with a separate deletion order.
Queries arrive only during timed search phases; future deletions and exact live-set answers are
unavailable to the submission.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
