# GPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CUDA-enabled PyTorch, TorchVision, TorchCodec, and FAISS GPU, together with the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `Pillow`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-gpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, `pydantic-settings`, `bitsandbytes`, `gemlite`, `hqq`, and `termcolor`.

Python and pip are available at `/opt/conda/bin/python` and `/opt/conda/bin/pip`.

The image also includes the CUDA 13.0 toolkit and runtime, Java 21 runtime, Node.js and npm, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Task resources and tools

The task provides one GPU, 16 CPU cores, 16 GiB RAM, no swap, 4 GiB shared memory and a limit of 2,048 processes/threads. Shared memory counts toward the RAM limit. The total task storage allowance is 64 GiB. CPU-only retrieval is permitted.

Data, models and tools are read-only under `/task/data`, `/task/models` and `/task/runtime`. Work under `/app`; only `/app/submission` transfers to final evaluation. Add `/task/runtime` to the Python import path to use its modules. The task instruction defines submission interfaces, timing, storage accounting and scoring.

The working submission is installed under `/app/submission`. A read-only original is available at `/task/starter/` and may be copied to a new working directory. Keep its `retriever_service.py` when using the supplied `prepare.sh`. `/opt/conda/bin/python /task/runtime/score_dev.py --predictions FILE` checks public predictions containing `query_id`, `ids` and `elapsed_sec`; it reports development quality using self-reported times, not final efficiency.

## Fixed-probe API

`compact_probe.load_probe('/task/models/base')` returns a probe with `model` (a Qwen2Model decoder), `config`, `cpu_embedding`, `output_token_ids`, `embed(input_ids)` and `output_rows(token_ids)`. `embed` returns GPU embeddings from the fixed input table. `output_rows` accepts original tokenizer IDs and returns their original BF16 head rows on CPU; matrix row positions are not tokenizer IDs. Read dimensions from `config`.

The serialized decoder uses bitsandbytes NF4/double quantization and BF16 computation. The complete input vocabulary is retained, while the output head is a diagnostic subset covering every delivered marked target token. It supports selected-token logits and comparisons, not full-vocabulary cross-entropy or unrestricted generation.

For probe inference, the supplied token embeddings can be passed as `inputs_embeds` with `attention_mask` and `use_cache=False`. The hidden state at `j-1` predicts marked position `j`; the corresponding output rows must be on the same device for logit computation. Preserve all marked positions and synchronize GPU work before returning a response.

Fixed-weight gradients are permitted, but optimizer updates to the probe/tokenizer are not. Query-dependent features, gradients and rankings must be recomputed for each execution, including repeated query IDs. Only training-derived state may persist across requests. Record self-built frozen artifacts and their generation settings in `submission.json` as specified in the task instruction.
