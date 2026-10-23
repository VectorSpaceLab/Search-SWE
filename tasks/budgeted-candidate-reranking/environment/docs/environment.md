# Runtime

Shared image: `docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` (Linux amd64, CUDA 13.0). Python `/opt/conda/bin/python`, PyTorch 2.9.0+cu130, Transformers 5.15.1, Accelerate 1.15.0, psutil 7.2.2, compilers and standard retrieval packages are installed; task addition is `nvidia-ml-py==13.580.82`. The coding CLI is Codex 0.164.0. No strategy is installed under `/app`; optional replaceable baselines are under `/task/baselines`, described in `available_resources.md`.

Resources: 16 CPUs, 32 GiB aggregate RAM, 40 GiB task storage including 4,079,434,577 fixed model bytes, one A100-SXM4-40GB with a 24 GiB total memory allowance and 22 GiB trusted allocator cap. The agent has 7200 seconds; final verification has 9000 seconds including the independent audit. Network is disabled for task code. The coding agent's own provider connection is managed by the harness separately. No submission APIs or judge credentials are supplied.

Read-only inputs: `/task/data/public.jsonl.gz`, `/task/data/public-qrels.json`, `/task/docs/`, `/task/runtime/`, `/task/models/Qwen3-1.7B`. The strategy gets each query on stdin, rather than reading a test file. Model weights remain inaccessible to the unprivileged final strategy. Development runs as root so the trusted runner can set up the kernel boundary; final strategy execution is always UID 10001, with no GPU. The submission and coding trajectory transfer to the separate verifier. Its final copy is read-only and each query gets fresh `/work`. No symlinks or special files are accepted.

Linux Landlock ABI >=3, libseccomp, cgroup v2 aggregate memory enforcement, compatible NVIDIA driver and Container Toolkit are runtime prerequisites. The trusted runner checks these instead of silently dropping isolation. Both Compose phases use `count: 1`; Docker selects one physical GPU. The runtime hardware and memory requirements still apply to that device.

Run `/opt/conda/bin/python /task/runtime/evaluate.py --submission /app/submission --output /app/dev-report` for all 43 public queries. `--queries`/`--qrels` may select an author-prepared public subset for development. Reports, bounded query stderr and model diagnostics appear below the requested output directory. Read the task instruction before implementing the JSONL client. Budget/timeout violations make the affected query fail; aggregate-resource/deployment/integrity failures invalidate the task. The request itself defines all numerical limits.

The whole container has a 256-task PID limit including the trusted runtime and strategy descendants.
OpenMP, OpenBLAS, MKL and NumExpr default to 16 threads per pool so imports fit alongside the coding CLI within that limit. The model's PyTorch thread count still follows `deployment.json`.

`/app` is mounted as a 24 GiB executable tmpfs in both phases, bounding writable development/submission storage independently of Harbor's metadata-only storage_mb. Its pages count toward the same 32 GiB cgroup RAM limit. The fixed 3.80 GiB checkpoint plus `/app`, `/work` and caches remain subject to the trusted 40 GiB total task-storage check. No system mount capabilities are granted to the container.

The independent verifier integrity audit uses `deepseek/deepseek-v4.1-flash` through OpenRouter. Only the trusted verifier has access to `openrouter.ai` and its audit credentials; submitted code retains its existing network and credential restrictions. The protected coding trajectory and submitted files are reviewed before final reward publication. Audit failures leave reward zero and produce `audit-status.json`.
