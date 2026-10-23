# Runtime and submission protocol

Both phases use `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0`.
Python is `/opt/conda/bin/python`. The image includes NumPy, FAISS CPU, SciPy,
PyArrow, SQLite FTS5, bm25s, hnswlib, psutil, a C/C++ toolchain and common search
libraries. No model weights or GPU are available. Task additions are public
baseline and diagnostic client code, not additional downloadable models.

Create `/app/search.sh`; it receives `--data-dir`, `--index-dir` and `--mode`
(`build` initially, `load` after a failed worker). It emits `{"op":"ready"}`
after all construction/loading and then implements the instruction's JSONL
query/score/result protocol. Use stderr for diagnostics. The stream is unbuffered
at message boundaries and each line is at most 1 MiB.

The agent has 7200 seconds. Development splits 16 CPU equivalents and 32 GiB
between the main program (15/31 GiB) and oracle (1/1 GiB). Final grading provides
16 CPU cores and one 32 GiB cgroup shared by the candidate and trusted scorer,
without swap. Construction/loading totals at most 3600 seconds. Each query is
single-concurrency and has 2 seconds and 20 document scores. The worker and all
children are suspended between queries; an invalid query causes a fresh load.

Storage is a real bounded filesystem. All fixed inputs, including private
vectors, count toward 64 GiB; immutable preinstalled system software is excluded. The writable remainder is computed from actual
asset sizes with a 512 MiB diagnostic reserve. Final `/app` is read-only; write
only under the supplied index directory or its parent `/work/runtime`.
The verifier drops to UID 10001, retains local Unix IPC, denies Internet sockets
and privilege escalation, and terminates the complete process family on failure.
