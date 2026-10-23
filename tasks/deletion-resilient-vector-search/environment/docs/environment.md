# Runtime and input contract

The CPU base is `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0`.
Use `/opt/conda/bin/python` (Python 3.12). The image verifies FAISS 1.15.0,
NumPy 2.5.2 and psutil 7.2.2; hnswlib 0.8.0 and C/C++ build tools are installed.
No GPU is provided.

Inputs are read-only under `/task/data/public/{sift,gist}`. Each contains
`base.f32`, `calibration.f32`, `deletions.i32` and `config.json`.
Current phase limits and scoring references are in `REFERENCES` in
`/task/tools/runtime_limits.py`. Each `calibration.f32` contains only 10 official-learn examples
to illustrate the protocol; the smoke checker defaults to all 10 and rejects
larger query counts. These examples do not estimate hidden-test performance.
Raw source archives,
hidden query vectors, hidden deletion lists and exact answers are never mounted
in the agent container. `/task/tools` has the public reference and smoke checker.

Create `/app/run.sh` and code under `/app`. During final verification `/app` is
read-only, UID 10001 runs the submission, and only the build message's `work_dir`
is writable. No symlinks in submitted artifacts. Compilation must therefore
write to work_dir and counts toward the build allowance. Use only supplied files
and installed tools. Process/thread cap: 512; maximum protocol line: 1 MiB.

The declared envelope is 16 logical CPUs / 64 GiB memory / 100 GiB task storage.
Queries are serial and restricted to one logical CPU, inherited by descendants;
the supervisor temporarily adopts the stopped worker's effective UID to set
affinity, then restores root before grading. No added container capabilities are
needed. The worker has no capabilities and cannot call sched_setaffinity, create
Internet sockets, enter namespaces, ptrace, or gain privileges. Local Unix IPC is allowed. OMP, MKL and
OpenBLAS start with one thread, with Intel OpenMP automatic affinity disabled.
Build/delete may explicitly use 16 threads. Aggregate RSS is sampled every 10 ms
while waiting and at boundaries; storage is sampled every 0.5 s and at boundaries.
The public runtime-limits module defines exact phase deadlines.

Development uses UID 10001 (`submission`) with no administrative privileges.
`/app`, `/tmp`, `/var/tmp`, `/home/submission`, `/dev/shm` and `/run/lock` share
a bounded ext4 filesystem. Keep all submitted files under `/app`; harness logs
are reserved for the harness and cannot store indexes or other task data. The
100 GiB allowance includes public input bytes, filesystem metadata and a 512 MiB
diagnostic reserve. The verifier uses the same quota mechanism for `/work`,
and subtracts submitted files too. Swap is disabled in both phases.
