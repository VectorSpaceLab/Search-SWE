# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes Java 21 runtime, Node.js 24.16.0 with npm 11.13.0, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

Create `/app/search.sh` with the JSONL service interface in the task instruction. It accepts `--data-dir`, `--index-dir` and `--mode build|load`, emits `{"op":"ready"}` when ready, and flushes each response. Use stderr for diagnostics; each protocol line is limited to 1 MiB.

During development the main container has 15 CPUs and 31 GiB RAM, and the local oracle has 1 CPU and 1 GiB RAM. Final grading shares 16 CPUs and 32 GiB RAM between the submission and trusted scorer, without swap. The task instruction specifies preparation and query limits.

Task storage uses a bounded disk filesystem. Fixed inputs and writable task files share 64 GiB, with a 512 MiB diagnostic reserve. The submitted directory is read-only during verification; build indexes under the supplied index directory; use TMPDIR for query-time writes after the prepared files become read-only. See `available_resources.md` for the development oracle and public tools.
