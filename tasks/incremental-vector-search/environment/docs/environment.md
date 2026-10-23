# Runtime

Both phases use `hanhainebula/search-swe-base:cpu-py3.12-1.0.0` on Linux x86-64.
Python is `/opt/conda/bin/python`; the shared CPU image includes NumPy, Faiss,
hnswlib 0.8.0, C/C++ build tools and the search libraries documented by that image.
No task-specific solver dependencies are installed. The shared image also provides
orjson3.12.0, used by the optional PQ reference for binary JSONL input/output. Read-only fixed NPY inputs
are under `/task/public`. The public exact reference and PQ baseline are
`/task/reference/exact_search.py` and `/task/reference/baseline_search.py`,
available read-only in both phases. Submit `/app/submission/run.sh` and its files.
Only that submission directory is transferred to the verifier.

The optional PQ reference controls OpenBLAS through threadpoolctl 3.6.0 and
Faiss's already-loaded MKL component through its thread-local C API. It permits 16 BLAS
threads during construction/insertion and restores one for queries. The MKL
handle does not load another threading runtime.

`/task/tools/profile_public.py` is an optional development-only latency check.
Run the supervisor as root; it starts the submission as UID 10001 with a minimal
environment, without Agent API credentials. It uses the calibrated CPU allocation,
all 16 CPUs for construction/insertion and one CPU for the entire query process
group. Its ten-stage default checks 1,000 different public probes at each stage/K,
including JSONL delivery and output. The default target reserves 10% against the
tightest calibrated budget across all ten stages. This is diagnostic guidance;
the official 10% limits and failure rules are unchanged.

```bash
python /task/tools/profile_public.py --dimensions 3072 \
  --output /app/profiles/check3072 -- bash /app/submission/run.sh
python /task/tools/profile_public.py --dimensions 1536 \
  --output /app/profiles/check1536 -- bash /app/submission/run.sh
```

Use a fresh directory outside the submission. Queries and duplicate insert rows
are sampled only from the initial matrix; queries can therefore be present in
the profile corpus, and this tool does not establish retrieval quality or promise
hidden-query latency. It has no hidden labels and produces no score. A shorter
`--stages`/`--queries` run checks the interface rather than full-workload capacity.
`--headroom 0` checks the minimum published limits without a safety margin.
The tool and its outputs are development aids, not transferred solver dependencies.

The verifier starts a persistent unprivileged process (UID 10001), permits writes
only to `/work/state`, isolates hidden paths with Landlock and denies network
and changes to CPU affinity with inherited seccomp filters. Linux must support
Landlock ABI >=1. The outer container enforces memory and CPU quotas. Query phases
pin the submission tree to one CPU. Build/insert limits and per-stage/K full-scan times are defined by
`LIMITS` in `/task/tools/runtime_limits.py`.

Verifier storage accounting samples logical file sizes in writable state, events, logs,
transferred submission and the current initial matrix every 100 ms. Each file is
also limited to 32 GiB; there is no aggregate filesystem hard quota. The
development container has the same declared 32 GiB budget, without a
kernel-enforced aggregate storage quota. CPU/memory
cgroups, zero swap and the 256-process/thread limit cover descendants. No extra
container capabilities are required. The execution limits permit 3600 seconds
for initial construction and 60 seconds for each insertion batch; every query
cell retains its independent 10%-of-exact-scan limit.

No specific CPU model or SIMD extension is required. The exact-scan reference
must be measured under the same conditions as the submission; changing the
evaluation machine requires recalibration of its query time budgets.

Both phases are restricted to the same 16 logical CPUs listed in the runtime module’s
`cpu_affinity`. For comparable local profiling, restrict every submitted thread
to one of those CPUs during queries. The frozen seconds remain authoritative
even if a local exact scan is slower. Check the minimum budget across all ten
stages for each K; the first stage may be more generous. For example:

```bash
/opt/conda/bin/python - <<'PYTHON'
import runpy
c = runpy.run_path('/task/tools/runtime_limits.py')['LIMITS']
for dimension, limits in c['datasets'].items():
    print(dimension, [min(row[i] for row in limits['full_scan_seconds']) * c['exact_scan_fraction']
                      for i in range(5)])
PYTHON
```

For local UID 10001 profiling, run the profiling supervisor and its candidate
under the same UID, or give the candidate its desired inherited affinity at
launch. A root supervisor without `SYS_NICE` cannot change a UID 10001 child's
affinity. The production controller handles this permission transition.
