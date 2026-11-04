# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources

The task provides 8 CPU cores, 32 GiB RAM and 100 GiB storage, with no GPU. Inputs and documents under `/task` are read-only; develop under `/app`.

The task instruction defines submission interfaces, workload limits and final-stage writable paths. See `available_resources.md` for permitted APIs and model IDs.
