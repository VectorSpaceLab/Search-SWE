# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes JDK 21, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task-specific execution

The runtime provides 8 CPUs, 8 GiB RAM, 8 GiB storage and no GPU. Numerical libraries default to one thread per process during development to avoid excessive threading on shared hosts. Development runs as `agentdev`; `/app` and your home directory are writable. Task data and system libraries are read-only.

`/app` starts empty. Submit `memory.json`, `build_index.sh`, `search.sh` and `answer.sh` there. Only declared artifacts are transferred to the separate verifier; development home files, extra installed packages and running services are not transferred. No local model weights are provided under `/opt/models`.

Evaluation runs index construction, retrieval and answering as an unprivileged user with read-only submission files and separate filesystem permissions. Use the supplied output directory for runtime scratch files. The task instruction defines each stage's inputs and limits; [available_resources.md](available_resources.md) documents the answering API transport.
