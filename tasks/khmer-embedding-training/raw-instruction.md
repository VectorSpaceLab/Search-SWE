# Khmer-to-English Embedding Retrieval

## Task Description

Build an embedding model and a search system for finding English documents with Khmer questions. Train the supplied multilingual-e5-large model for this collection and provide an executable indexing and retrieval pipeline.

## Requirements

### Resource limits

- You have 6 hours, one A100 with 40 GiB GPU memory, 8 CPU cores, 32 GiB RAM and 100 GiB working storage.
- Network access is unavailable.
- Use only the supplied local resources.
- Treat `/task` as read-only and put your work under `/app`.

### Execution and file permissions

- `build.sh` must create the requested index directory from the supplied collection.
- The index directory does not initially exist; its parent exists and is writable.
- Construction has a 12-hour limit.
- A previously built collection index or cached retrieval results must not be used as the submission.
- `run.sh` must use the resulting index and support repeated invocations, with a 30-minute limit per invocation.
- The index is read-only during retrieval.
- Honour the supplied paths rather than hard-coding the example paths.
- Build and retrieval run as separate non-root users, each with a writable working directory and `TMPDIR`; `/app` and task inputs are read-only.
- Use those writable directories for temporary files, honor the supplied output path, and do not write caches beside the checkpoint or assume a writable system temporary directory.
- The indexing and retrieval environment provides the same embedding backbone, one GPU, 8 CPU cores and 32 GiB RAM, without the optional generative model or network access.

### Build interface

The build command accepts the following arguments:

```bash
/app/build.sh \
  --corpus /task/data/corpus.parquet \
  --index-dir /path/to/index
```

### Query interface

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

### Input and output contract

Each query is a JSONL row with `id` and `question`:

```json
{"id":"query-001","question":"..."}
```

For each query, write one JSONL row in the same order, containing the same `id`, `indices` and `scores`. Return 100 unique document positions, ranked by decreasing relevance score. Positions are zero-based row numbers in the supplied Parquet file. Scores must be finite numbers; ties are ordered by ascending document position. If a collection has fewer than 100 documents, return all its positions.

```json
{"id":"query-001","indices":[42,7,103],"scores":[0.91,0.85,0.72]}
```

The abbreviated example illustrates the fields and ranking order. Do not write progress messages to the result file.

## Available Validation Data

The collection at `/task/data/corpus.parquet` has `_id`, `title` and `text` columns. Three examples are available in `/task/data/examples.jsonl`, with `id`, `question` and `answers` fields; the questions are in Khmer and the answers are in English. No other labeled training data is supplied. The embedding backbone is at `/task/models/multilingual-e5-large`, and an optional local generative model is at `/task/models/Qwen3.5-9B`.

## Expected Artifacts

Provide executable `/app/build.sh` and `/app/run.sh`, with any supporting files they need under `/app`.

Save the trained weights to `/app/submission/model/model.safetensors`, overwriting that file if it exists. Put `config.json` and the unchanged tokenizer files in the same directory with their original filenames. Preserve the backbone architecture, parameter names, shapes and architecture configuration. The directory must be a complete, self-contained Hugging Face checkpoint that `AutoTokenizer.from_pretrained` and `AutoModel.from_pretrained` can load with `local_files_only=True` and `trust_remote_code=False`.

```text
/app/
├── build.sh
├── run.sh
└── submission/
    └── model/
        ├── model.safetensors
        ├── config.json
        └── ...  # unchanged tokenizer files
```

## Verification

After development, Harbor transfers the declared artifacts to a separate verifier and evaluates the system on the held-out split. The verifier checks the following items:

1. **Task and resource compliance.** The submission must use the supplied inputs and permitted resources, follow stage isolation, and avoid hidden labels or hard-coded evaluation answers.
2. **Executable behavior.** The required commands must follow the interfaces, filesystem permissions and time limits above and support the specified repeated calls.
3. **Output validity.** Results must satisfy the task-specific schema, identifiers, bounds and ordering rules. An invalid checkpoint, a failed or timed-out build or retrieval command, or invalid retrieval output gives zero for the entire submission.
4. **Search quality.** Raw quality is Recall@100: a query succeeds when at least one of its first 100 retrieved documents contains an accepted answer under the answer-token matching rule. Recall@20 is reported separately.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
