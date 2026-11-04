# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources and execution limits

The task provides 4 CPUs, 32 GiB RAM, 100 GiB storage and no GPU. The Agent phase allows 120 minutes for implementation, validation and debugging.

During verification, `build.sh` must complete within 1,800 seconds. After that single build, `run.sh` is invoked sequentially with one query per input file and an **8-second wall-clock deadline** per invocation, including startup, index loading, all processing, API waits and retries, and output. Unused time cannot be pooled across queries. A timeout stops that invocation and ignores its output; only that query earns zero and remains in the Accuracy@1 denominator. Build failures/timeouts and other execution/output violations invalidate the submission. Both commands must return exit status 0 to count as successful.

The same index directory and any build-started background service persist across query invocations, including after a query timeout. Future evaluation queries are not revealed in advance. Prepare reusable artifacts during the build. The 4-CPU limit controls local compute; it is not a limit on concurrent network requests.

## Verification environment

Verification uses a fresh, separate container with the same base runtime. Only `/app` is transferred; packages installed elsewhere during development do not transfer. Keep all required code, dependencies and resources under `/app`.

The submission runs as a non-root user with `/app` read-only. The verifier supplies a fresh writable `--index-dir`; use it for indexes, caches, temporary files and service state. The result file is written separately at `--output`. Honor `TMPDIR` and the supplied paths, which may differ from development paths. Public validation files need not be available during verification.
