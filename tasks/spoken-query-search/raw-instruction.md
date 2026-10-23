# Spoken-Query Document Search

## Task Description

Build a document search system for spoken requests whose transcription may contain mistaken words or names. Each request provides the output of a fixed speech recognizer, including its best transcription, alternative hypotheses and relative hypothesis scores.

## Requirements

### Resource limits and workload

- The environment has 8 CPU cores, 32 GiB RAM and 100 GiB storage and one 40 GiB GPU.
- Development has a two-hour budget, index construction up to 180 minutes, and query calls follow the workload below.
- Calls may be repeated with different input files.
- Use at most five retrieval formulations and at most 50 query-document pairs for further reranking per request.
- The speech recognizer is fixed; additional speech recognition is not available.

- Process requests independently; do not combine hypotheses or results from different requests.
- Data, model and documentation mounts are read-only.
- Place all other required runtime files under `/app`.

- The system must handle workloads of up to 4,600 requests in 4 calls of at most 1,200 requests.
- Each call has an independent 1,350-second allowance; time used by one call does not reduce another.
- Completed valid JSONL rows remain usable if a query call times out; missing or malformed rows are unsuccessful.
- A failed query command other than a timeout invalidates that call.

### Execution and file permissions

- During verification, build and query commands run as a non-root user with `/app` and supplied inputs read-only.
- The passed index directory already exists and is writable during construction, but its parent directory is not writable.
- Create build files and temporary directories inside the index directory or the supplied `TMPDIR`; do not create siblings or rename the index directory itself.
- The completed index becomes read-only for retrieval.
- Query results, caches and temporary files belong in the writable output directory or the supplied `TMPDIR` and `XDG_CACHE_HOME`.
- Honor the passed paths rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Create executable `/app/build.sh` and `/app/run.sh` and their supporting files under `/app`:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /work/index
```

### Query interface

```bash
/app/run.sh \
  --index-dir /work/index \
  --queries /work/input/queries.jsonl \
  --output /work/output/results.jsonl
```

### Input and output contract

Each input JSONL row contains `query_id`, `domain`, `language`, `one_best` and `hypotheses`. Each hypothesis has `text`, `mean_log_probability`, `confidence` and `words`. Word entries give the word, its character span in that hypothesis and its confidence. Return the same `query_id` and a `results` list of at most ten distinct documents from that domain, each containing `doc_id` and a finite numeric `score`, in descending score order. Write diagnostics to stderr.

## Available Validation Data

The supplied document collections are at `/task/data/corpus/`. Each collection has a JSONL file with `doc_id`, `domain`, `language`, `title` and `text`. Local text encoder weights are available at `/task/models/encoder/`.

Public queries and relevance labels are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Labels contain `query_id` and `qrels`, a mapping of document IDs to relevance grades. Clean question text and query audio are not provided. The remaining transcriptions and labels are not supplied.

You may use the public examples to implement and check the complete build and query path during development. Include all required implementation files under `/app` so the system runs after a fresh start with the supplied inputs.

## Expected Artifacts

Submit executable `/app/build.sh` and `/app/run.sh` together with every implementation file and learned parameter required at runtime under `/app`.

```text
/app/
├── build.sh
└── run.sh
```

## Verification

After development, Harbor transfers the declared artifacts to a separate verifier and evaluates the system on the held-out split. The verifier checks the following items:

1. **Task and resource compliance.** The submission must use the supplied inputs and permitted resources, follow stage isolation, and avoid hidden labels or hard-coded evaluation answers.
2. **Executable behavior.** The required commands must follow the interfaces, filesystem permissions and time limits above and support the specified repeated calls.
3. **Output validity.** Results must satisfy the task-specific schema, identifiers, bounds and ordering rules. The failure and timeout behavior follows the contracts above.
4. **Search quality.** Raw quality is graded nDCG@10, averaged within each collection and acoustic condition and then equally across the six collections and four conditions.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
