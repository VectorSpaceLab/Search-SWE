# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources

The task provides 1 CPU, 32 GiB RAM and an 80 GiB total storage allowance, with no GPU. Build and search must be single-process and single-threaded. Submission logic must be Python; installed packages may be used through their normal APIs. Formal execution is offline.

Task inputs and documentation are read-only under `/task`. The editable starter is under `/app`; a read-only original is at `/baseline-starter`. Build all persistent state under the supplied index directory. The index and submission source become read-only for search; use the supplied output and temporary paths for writes.

The task instruction defines quality gates, full wall-time measurement, time limits and reward. See `available_resources.md` for the supplied starter and its optional documentation.
