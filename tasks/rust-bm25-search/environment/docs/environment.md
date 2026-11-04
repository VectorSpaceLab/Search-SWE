# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources

This task uses Linux x86_64 with 4 CPUs, 16 GiB container memory including children and page cache, 64 GiB workspace, a 256-PID container limit and no runtime network. The development budget is 10,800 seconds.

Rust 1.85.1 and Cargo are installed at `/opt/rust`. `/opt/cargo` contains the locked generic dependency cache. The source starter is at `/app/submission` and does not implement retrieval. Keep build products outside the source submission with `CARGO_TARGET_DIR=/app/build`:

```bash
cargo build --release --offline --locked
```

After implementing the CLI, a three-passage synthetic check is available; it does not estimate full-dev quality:

```bash
python /task/smoke.py --binary /app/build/release/bm25-search
```

Only `/app/submission` transfers. Search runs as an unprivileged user with an immutable index; the raw corpus and writable caches are unavailable. The task instruction defines source/output limits, compilation and indexing budgets, permitted system capabilities, and cold/warm timing rules.

Installed search engines such as Pyserini are not permitted in the submission. The timing and quality reference uses Pyserini 1.4.0 with BM25 k1=0.9, b=0.4. See `available_resources.md` for input schemas and allowed dependencies.
