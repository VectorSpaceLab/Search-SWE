# Visual-Document Evidence Page Retrieval

## Task Description

Locate the pages that support a question about a report's figures, tables or layout so that the original material can be inspected. Build a search system that returns a compact set of supporting pages within the specified document. Include the pages needed to check the request, while avoiding unrelated pages.

## Requirements

### Resource limits and workload

- You have six hours for implementation and checking, eight CPU cores, 32 GiB RAM, 100 GiB storage and one 40 GiB GPU.
- The supplied encoders are fixed.
- An optional scoring or adaptation component may have up to five million trainable parameters and use up to 45 minutes of training.
- Per request, query-dependent page-token or region comparisons and learned pairwise scoring may inspect at most 40 candidate pages; corpus-wide text processing, global representations and gallery-only preprocessing are allowed.
- No external model, dataset or API is available.

- The query workload contains at most 600 requests in two calls, each with an independent 2,700-second allowance.
- Completed valid rows remain usable if a call times out; missing or malformed rows are unsuccessful.
- Honor the supplied paths.
- The submitted system must work after a fresh start with the same inputs.

### Execution and file permissions

- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Provide executable `/app/build.sh` and `/app/run.sh`, with all supporting code and learned files under `/app`. Index construction uses:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir DIR
```

The build command must return successfully within 3,600 seconds.

### Query interface

Requests use:

```bash
/app/run.sh \
  --index-dir DIR \
  --queries JSONL \
  --output JSONL
```

### Input and output contract

Each input row contains `query_id`, `doc_id`, `question`, `domain` and `language`. Return one JSONL object per input, preserving `query_id`, with a `results` list of at most ten distinct pages from the specified document. Each item contains `page_id` and a finite numeric `score`, in nonincreasing score order. No answer text or bounding box is required. Write diagnostics to stderr.

## Available Validation Data

The page collection is at `/task/data/corpus/`. Its `records.jsonl` lists `page_id`, `domain`, `doc_id`, `page_number`, `image_path`, `markdown`. Paths are relative to that directory. The images are rendered document pages and the text is uniformly extracted from the documents. Local model weights are available at `/task/models/page-encoder/` and its underlying model at `/task/models/vision-backbone/`. These resources are read-only.

Public requests and page-relevance annotations are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Use these examples to check the complete build and query path. The remaining requests and labels are not supplied.

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
4. **Search quality.** Raw quality is set F1 between returned pages and the complete reference evidence-page set, averaged across held-out questions. Both missing evidence pages and extra pages reduce this metric. Domain-level results are reported separately.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
