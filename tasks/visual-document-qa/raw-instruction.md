# Visual-Document Question Answering

## Task Description

Build a system that answers questions using the supplied long documents. Relevant information may occur in body text, tables, charts or several pages. If the document does not contain the requested information, say so.

## Requirements

### Resource limits and workload

- The environment provides 8 CPU cores, 32 GiB RAM and 100 GiB storage, with no GPU.
- Development has a two-hour budget.
- Index construction may take up to four hours.
- The system must handle up to 2,500 requests in two calls of at most 1,250 requests, with an independent 10,800-second allowance per call.
- Completed valid JSONL rows remain usable after timeout; missing or invalid rows are unsuccessful.
- A command failure other than timeout invalidates that call.
- Honor the supplied index and output paths.

### Execution and file permissions

- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Create executable `/app/build.sh` and `/app/run.sh`, with the code and files they need under `/app`:

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
  --output /work/output/answers.jsonl
```

### Input and output contract

Each input JSONL row contains `query_id`, `doc_id` and `question`. Return one JSONL row for each query, with the same `query_id`, an `answer` string and a `pages` list of the supporting document's page numbers. Page numbers start at one. Give the final answer directly, including units where applicable; a list answer may be expressed as a list in the string. Use an empty `pages` list when no supporting page exists. Write diagnostics to stderr.

## Available Validation Data

The collection is at `/task/data/corpus/`. Its `records.jsonl` contains `doc_id`, `pdf_path`, `text_path` and `page_count`. Paths are relative to that directory. The PDFs are the original documents; the text files contain uniformly extracted text for each page. You may render and read the PDFs directly.

Public requests and reference answers are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. The remaining questions are not provided. The original corpus and public examples are read-only.

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
4. **Search quality.** Raw quality measures answer correctness against the reference answers, including numeric, list and unanswerable questions. The answer-comparison rules and grouping used for the final average are defined in [README.md — Search Quality](README.md#search-quality). Evidence-page precision, recall and F1 are reported separately and do not affect the answer score.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
