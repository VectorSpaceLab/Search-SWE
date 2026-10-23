# Narrative-Clue Search

## Task Description

Build a search system for users who recall a work through scattered details. A request may contain a long description, comparisons, uncertain memories and background information. Return documents from the supplied collection.

## Requirements

### Resource limits and workload

- The environment has 8 CPU cores, 32 GiB RAM and 100 GiB storage, without a GPU.
- The OpenRouter and Jina APIs listed in the resource document are available.
- Development has a two-hour budget, index construction up to 60 minutes, and the query workload described below.
- Calls may be repeated with different input files.
- Data and documentation mounts are read-only; write generated indexes to the supplied index directory.

- The system must handle workloads of up to 450 requests in 2 calls of at most 225 requests.
- Each call has an independent 2,700-second allowance; time used by one call does not reduce another.
- Completed valid JSONL rows remain usable if a query call times out; missing or malformed rows are unsuccessful.
- A failed query command other than a timeout invalidates that call.

### Execution and file permissions

- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Create executable `/app/build.sh` and `/app/run.sh`, with their supporting files under `/app`:

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

Each input JSONL row contains `query_id` and `question`. Return the same `query_id` and a `results` list of at most ten distinct documents, each with `doc_id` and a finite numeric `score`, in descending score order. Write diagnostics to stderr.

## Available Validation Data

The collection is at `/task/data/corpus/records.jsonl`. Each row contains `doc_id`, `title` and the full article `text`.

Public queries and relevance labels are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Labels contain `query_id` and `qrels`, a mapping of document IDs to relevance grades. Original sentence-level annotations for these public queries are at `/task/data/training/sentence_labels.jsonl`. The remaining queries and labels are not supplied.

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
4. **Search quality.** Raw quality is nDCG@10 using the original relevance judgments, averaged equally across held-out questions. Category-level results are diagnostics and do not change query weights.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
