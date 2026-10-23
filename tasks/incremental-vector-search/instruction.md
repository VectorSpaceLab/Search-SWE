I need a vector search service that stays usable while new items are inserted,
and can return either a few hundred or a thousand nearby items from the same
index. The vectors have already been computed. Please implement the service so
that it recovers as many exact L2 neighbors as possible while meeting each
insertion and query workload's time budget. You may choose any indexing method;
there is no required algorithm, training step or starter implementation.

The supplied Qdrant DBpedia vectors form two independent collections, with
1536 and 3072 dimensions. Their
initial C-order float32 NPY matrices are `/task/public/<dimension>/initial.npy`,
each containing 105,000 vectors with IDs 0 through 104999. Original float32 L2
defines correctness; preserve that metric without normalizing the canonical vectors.
Internal projections, quantization and compressed indices are permitted for
approximate candidate search. Each collection receives ten batches
of 1,000 new vectors, assigned consecutive IDs starting at 105000. Immediately
after each insertion batch, the service receives 1,000 held-out queries at each
of K=100,200,400,800,1000, in that order. The same queries and order are used at
all five K values. Maintain one index across these stages and K values; rebuilding
the entire index after every batch is forbidden. The two collections use separate
processes and indices. Future inserts and queries arrive only through their events.

Put your entry point and supporting files under `/app/submission`.
The evaluator transfers only that directory and runs `bash /app/submission/run.sh`
in a fresh container. Both phases use the same supplied CPU base runtime.
It does not transfer agent-installed packages or running
services. Include source and compile at startup if necessary, or provide a
compatible executable. The process stays alive and reads one JSON request per
stdin line, returning one flushed JSON response per stdout line. There is one
outstanding request at a time; keep diagnostics on stderr, send no unsolicited
stdout, and keep each response within 128 KiB.
Make the submitted entry point and source readable, and binaries executable, by UID 10001.

A build request looks like
`{"op":"build","vectors":"/task/public/1536/initial.npy","dimension":1536,"count":105000,"threads":16,"state_dir":"/work/state"}`.
Load and index the matrix, then reply `{"ok":true}` when ready. Rows have
consecutive IDs. Startup, imports, compilation and public warmup count toward
build time. Write all mutable files beneath the supplied `state_dir`.

An insert request looks like
`{"op":"insert","vectors":"/work/events/insert.npy","count":1000,"first_id":105000,"threads":16}`.
The file contains a float32 matrix. Reply `{"ok":true}` only when every new row
is searchable, since a query can follow immediately. Copy or load what you need
before replying; the file is then removed. Index repair and maintenance count
as insertion work. Maintenance continuing into a query phase consumes query time.

A search request has `op`, `vector` and `k`, for example
`{"op":"search","vector":[0.1,0.2],"k":100}` with a full-dimensional vector
in a real request. Return paired lists such as
`{"ids":[12,35],"distances":[0.2,0.5]}`. Return at most K IDs and finite,
nonnegative L2 distances. Partial or empty results are allowed. A valid ID can
only earn one hit; duplicate, unknown or invalid ID/distance entries earn none.
Missing results remain misses. A malformed response, failed query, or more than
K results gives that query zero recall, without removing it from the denominator.
If the process or response framing is lost, that collection fails because its
remaining events cannot be executed.

You have 120 minutes for development, 16 CPU cores, 32 GiB total
container memory and 32 GiB storage. No GPU is provided, and the submitted
program cannot use external model services or network APIs. Build and insertion
can use all 16 CPUs. Query processing, including
background work, must be single-threaded with concurrency one. The evaluator
restricts every submission thread/process to one CPU during queries; do not use
parallel query workers, though idle library thread pools are fine. Verification
runs under UID 10001 with inherited process isolation, no network, and read-only
submission, runtime and input files. Only the supplied state directory is writable.

Use `/task/tools/runtime_limits.py` for the public build/insertion hard limits
and frozen exact-scan times. These published seconds are absolute limits for this
run; your own slower exact-scan measurement does not increase them. Check all
ten stages, since their budgets differ. Both phases use the 16-CPU allocation
recorded in calibration; local query profiling should pin all worker threads to
one of those CPUs, matching the verifier. Each 1,000-query stage/K cell must take at most 10%
of its own reference time. Saving time in one cell never increases another's
allowance. The entire cell is timed, including request delivery, retrieval,
distances, selection, query caches and output. The evaluator stops the submission
while it scores responses; only these trusted pauses are excluded. Warmup happens
once before insertions, using only `/task/public/<dimension>/warmup.npy`, and
counts toward build time. Do not move held-out query computation outside query
time. `/task/reference/exact_search.py` is the public full-scan implementation and
protocol example, not a baseline expected to pass the 10% gate.

Recall for a query is the number of unique valid returned IDs in its exact Top-K,
divided by K. Your primary score counts actual missed neighbors across all
queries, stages and K values. If a query returns h valid hits at K, add `K-h`
to C_d. Each requested exact neighbor has the same weight; a K=1000 query
therefore contributes ten times as many positions as a K=100 query.
There are `10 * 1000 * (100+200+400+800+1000) = 25000000` positions per
collection: `micro_recall_d = 1 - C_d / 25000000`. The unweighted average of
the 50 cell recalls is also reported as macro recall, but is not the primary
aggregation. The exact target set must match the requested K.

The optional fixed reference implementation is `/task/reference/baseline_search.py`.
Its full-workload `baseline_micro_recall` and `baseline_missing_neighbors` are
public in `/task/tools/runtime_limits.py`.
If C_base,d is the public baseline's count, the collection value is
`G_d = clip(1-log(1+C_d)/log(1+C_base,d), 0, 1)`. Equal or worse recall than
the baseline earns zero; removing all errors earns one. The logarithmic scale
rewards successive orders of magnitude of error reduction near perfect recall.
Any build/insertion failure or timeout, cell timeout, memory/storage violation
or failed execution gives that collection zero. The final score is
`50 * (G_1536 + G_3072)`; normalized reward is their mean in [0,1]. Speed
within budget adds no points. Raw recall, complete-query rates, error counts,
timings and resources are reported separately. A trajectory/code audit checks that the index is incremental and
that the solution has not accessed hidden data, exploited event visibility,
manipulated grading/resources, hard-coded evaluation answers or obtained external
answers. A proven violation gives the whole task zero; an unavailable or failed
audit invalidates the measurement. Public-example tuning and legitimate caches
built inside their measured query phases are permitted.

For local checks, `/task/public/<dimension>/development/{initial,inserts,queries}.npy`
contains a small independent workload derived only from public initial vectors:
10,000 initial vectors, ten batches of 100 insertions and 100 queries, and the
same K values. Its queries are excluded from its own corpus and are disjoint
from hidden queries. Run the exact reference on that event sequence to obtain
targets and compare your service. Read `/task/docs/environment.md` and
`/task/docs/available_resources.md` for the supplied tools and resource policy.

You can also use the optional development-only `/task/tools/profile_public.py`
to check latency with a full-size index through ten successive insertions and
1,000 distinct queries per stage/K. It derives all query and duplicate-insert
rows from public initial vectors, runs your process as UID 10001, and restricts
every query thread to one calibrated CPU. The default diagnostic target leaves
10% below the tightest official budget across all ten stages. It checks timing
and response structure, without computing retrieval quality or a task score.
Public-probe timings do not guarantee hidden-query timings; validate capacity
after successive insertions because later query cost can differ from the first
batch. For example, run this as root in the agent container:
`python /task/tools/profile_public.py --dimensions 3072 --output /app/profiles/check1 -- bash /app/submission/run.sh`.
Choose a fresh output directory outside `/app/submission`. This development
tool and its outputs are not transferred as solver dependencies. The official
workload, 10% query limits and scoring formula remain the same.

Exact L2 targets use the pinned Faiss direct float32 distance kernel. When the
Kth distance has a tie, any otherwise valid ID at exactly that distance may earn
a hit. The verifier recomputes such distances; submitted distances cannot prove
a boundary tie. No numerical tolerance expands the true neighbor set.

No particular CPU model or SIMD instruction set is required. The organizer
measures the fixed exact reference in the same evaluation environment as the
submission, under identical CPU, query-order and warmup conditions. Locally
measured query budgets are frozen before the coding-agent trial. Moving the
evaluation to a different environment requires new reference measurements;
wall-clock budgets must not be copied between different machines.
