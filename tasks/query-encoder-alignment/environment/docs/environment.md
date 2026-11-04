# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes the CUDA 13.0 toolkit and runtime, Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources

The task provides 8 CPU cores, 32 GiB RAM, 100 GiB storage and one GPU.

Inputs are read-only under `/task/data` and `/task/models`. `/task/data/doc.npy` contains 8,674 × 2,560 float32 vectors, with matching identities and texts in `corpus.jsonl`; public queries and labels are under `/task/data/validation`. Preserve the fixed vectors and row correspondence.

`/app/quality_reference` provides the frozen 0.6B ridge quality baseline and reproduction commands. `/app/time_reference` provides the 4B timing reference. The final backbone must derive from the supplied 0.6B model; the 4B model is available during development but inaccessible to the unprivileged final process.

Only `/app/submission` transfers to the verifier. Its runtime copy is read-only; use the supplied output directory or `TMPDIR` for scratch. The task instruction defines time limits, full wall-time measurement and deterministic repetition requirements.
