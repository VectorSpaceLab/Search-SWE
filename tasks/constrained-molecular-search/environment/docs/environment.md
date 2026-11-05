# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes the CUDA 13.0 toolkit and runtime, Java 21 runtime, Node.js 24.16.0 with npm 11.13.0, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

The task additionally installs RDKit 2024.3.5, DuckDB 1.3.2, TensorBoard 2.20.0, LightGBM 4.6.0 and nvidia-ml-py 12.560.30. APEX and its GPU top-k extension are installed from bundled sources. One GPU is provided. Linux Landlock ABI 3 or newer, seccomp, cgroup v2 and a compatible NVIDIA runtime are required.

Read-only inputs are under `/task/library`, `/task/models`, `/task/train` and `/task/dev`. Public helpers are under `/task/runtime`. The `Library` helper in `library.py` provides `id_to_name`, `name_to_id`, `id_to_smiles`, `id_to_key` and `iter_smiles` for the supplied library. Property units are Da for `mol_wt`, RDKit Crippen logP for `logp`, counts for hydrogen-bond and rotatable-bond fields, and square angstroms for `tpsa`; rotatable bonds use RDKit's default strict definition.

Task files use disk storage. The 32 GiB RAM limit includes `/dev/shm`; its IPC capacity is 2 GiB. Fixed inputs, submission files, indexes and caches share the 64 GiB storage budget. Final code writes under its supplied index and scratch directories and must honor `TMPDIR`. Processes must permit procfs descriptor inspection for storage accounting; disabling dumpability or preventing inspection invalidates the submission.

The public self-check uses the original validation library and its supplied candidate membership. It makes the submission read-only for child execution; the development root user can restore write permission to continue editing.

```bash
PYTHONPATH=/task/runtime /opt/conda/bin/python /task/runtime/evaluate.py \
  --library-dir /task/dev/library --private-dir /task/dev \
  --output-dir /app/development-report
```

The optional `/task/runtime/baseline.py` exports `prepare` and `Searcher`. Its command-line options and configuration are in that file. The task instruction defines the submission interface, request budgets and scoring; `available_resources.md` records source terms and data semantics.
