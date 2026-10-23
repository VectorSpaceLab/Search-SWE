# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes the CUDA 13.0 toolkit and runtime, JDK 21, Node.js 24.16.0 with npm 11.13.0, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

An additional Python environment is available at `/opt/stella/bin/python`, with
`transformers==4.44.2`, `tokenizers==0.19.1`, `huggingface-hub==0.36.0`,
`sentence-transformers==3.0.1`, `einops==0.8.1` and `peft==0.12.0`. It shares the base image's
CUDA-enabled PyTorch. Both Python environments are available during verification.
