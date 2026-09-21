# CPU Docker Environment

This task uses `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0` on Linux x86-64.

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes JDK 21, Node.js 24.16.0 with npm 11.13.0, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.
## Task runtime

The task adds Codex CLI 0.147.0, Pi 0.85.1 and Claude Code 2.1.273 to the shared image. These tools are preinstalled for the benchmark launcher; setup does not require package-registry access.

Development runs as root in `/app`, with 8 CPUs, 8 GiB RAM, 8 GiB storage and no GPU. Numerical libraries default to one thread per process. No local model weights are supplied under `/opt/models`.

The conversation history at `/task/data/history.jsonl`, public examples at `/task/data/validation/` and documents at `/task/docs/` are read-only mounts. API access is described in [available_resources.md](available_resources.md). Submission interfaces and evaluation-stage permissions are defined in the task instruction.
