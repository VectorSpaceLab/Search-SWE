# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes the CUDA 13.0 toolkit and runtime, Java 21 runtime, Node.js 24.16.0 with npm 11.13.0, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

The task additionally installs `nvidia-ml-py==13.580.82`. One GPU is provided for the trusted fixed-model process. The final strategy runs as an unprivileged CPU process and uses the documented model interface.

Read-only inputs are under `/task/data`, `/task/models/Qwen3-1.7B`, `/task/runtime` and `/task/docs`. Optional starting strategies are under `/task/baselines`. Work under `/app`; its files use disk storage. Fixed inputs, submitted files and generated caches share the 40 GiB task-storage budget. Aggregate host RAM is 32 GiB.

The container permits 256 tasks, including the trusted runtime and strategy descendants. OpenMP, OpenBLAS, MKL and NumExpr default to 16 threads per pool; the model thread count follows `deployment.json`.

Linux Landlock ABI 3 or newer, libseccomp and cgroup v2 are required. Use `/opt/conda/bin/python /task/runtime/evaluate.py --submission /app/submission --output /app/dev-report` for the public self-check. The instruction defines the interface, query budgets and permitted deployment settings.
