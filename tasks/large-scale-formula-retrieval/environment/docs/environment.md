# CPU environment

Base: `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0`.
Use `/opt/conda/bin/python` and `/opt/conda/bin/pip`. Python 3.12, CPU PyTorch,
NumPy, SciPy, scikit-learn, transformers, sentence-transformers, FAISS CPU,
bm25s, rank-bm25, hnswlib, SQLite with FTS5, lxml and psutil are installed.
System tools include C/C++ build tools, JDK 21, bash, Git, curl, jq, unzip and
procps. No extra task Python packages or model weights are preinstalled.

`/task/data/public` and `/task/docs` are read-only. `/app`, `/tmp`, `/var/tmp`,
`/home/submission`, `/dev/shm` and `/run/lock` share bounded development storage.
Only `/app/submission` is transferred. During verification it is read-only;
write to the supplied index/work paths, with `HOME` and `TMPDIR` pointing to
`/work/runtime` during building and `/serve/runtime` during serving. Submission execution uses UID 10001.

2 CPU cores, 4 GiB container RAM, no swap/GPU. Total storage is 64 GiB,
including public data and model artifacts. A bounded filesystem enforces writes;
512 MiB plus filesystem metadata is reserved. The 7200-second development budget
is distinct from the final 3600-second build, 120-second loading, 30-second
three-query public warmup and 50-millisecond individual query limits. CPU affinity
and container memory limits cover descendants. Only one hidden query is in flight.

Public check: `/opt/conda/bin/python /task/tools/check_submission.py --submission /app/submission --index-dir /app/dev-index`.
Add `--skip-build` to reuse an index. The checker measures public relevance and
latency but does not replace final privilege, process-family, disk or memory enforcement.


Final serving uses an independent 40 MiB filesystem shared by the copied index,
reserved submission/model bytes, caches and temporary files. Its 4096 inodes and
metadata reduce usable bytes slightly. Building still has the 64 GiB overall
budget, including all public inputs, with 512 MiB diagnostics and 40 MiB serving
capacity reserved from its writable volume. The fresh build writes `/work/index`
and `/work/runtime`; after build termination, the verifier copies regular index
files/directories to `/serve/index` (read-only) and hides all of `/work`. The JSONL
load request provides `/serve/index` and writable `/serve/runtime`. Always honor
supplied paths. Fifty milliseconds includes input/output and suspension of all
submission processes. Only five 2021 development queries/labels are authorized.

Storage accounting uses the greater of logical size and allocated blocks per
regular file, counting shared hardlinks once. The physical serving filesystem
also needs its own metadata; both accounting and actual capacity apply.

The allocated submission/model files and completed index together must be at most **34 MiB (35,651,584 bytes)**, counting max(logical size, allocated blocks) per regular file and shared hardlinks once within each directory tree. This prepared-artifact limit applies before copying and is checked by both the public helper and final verifier. The separate **40 MiB (41,943,040 bytes)** physical serving filesystem also holds its metadata, reserved submission bytes, the index, all caches and serving-time temporary files; leave room for startup and query writes. The artifact limit reserves headroom rather than assuming the gross filesystem size is usable artifact space. Exceeding either limit gives overall zero.

The verifier additionally runs an independent trajectory/submission integrity review
using `deepseek/deepseek-v4.1-flash` through OpenRouter. Final reward requires a
successful accepting review. Its credentials and allowlisted API access belong
only to the trusted judge; submitted code retains its existing network restrictions.
The verifier protects a separate trajectory snapshot before running submitted code.
