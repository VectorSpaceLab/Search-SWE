# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, `pydantic-settings`, `peft`, and `nvidia-ml-py`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes the CUDA 13.0 toolkit and runtime, Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources

Public data and base models are mounted read-only at `/task/public` and `/task/models`. Work under `/app` or `/tmp`; place the final submission under `/app/submission`.

The public evaluation tool is `/task/runtime/evaluate.py`. Follow the task instruction for the submission interface and self-check command.
