# Multilingual Visual Document Page Search

## Task Description

Reports in several languages contain tables, charts and dense page layouts. The system must find the pages that support a question so that the original material can be opened and checked. Build a page search system over the supplied collection.

## Requirements

### Resource limits and workload

- You have 8 CPU cores, 32 GiB RAM, 100 GiB storage, one 40 GiB GPU and two hours to implement and check the system.
- Local model weights and processors are at `/task/models/page-encoder/` and `/task/models/vision-backbone/`.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the installed tools and permitted API resources.
- Use only those providers, endpoints and generative model IDs.
- Do not obtain evaluation questions, answers or relevance labels from outside the provided inputs, use external search services, or store API credentials in code, indexes or logs.

- The system must handle workloads of up to 14,500 requests in 2 calls of at most 7,250 requests.
- Each call has an independent 2,700-second allowance; time used by one call does not reduce another.
- Completed valid JSONL rows remain usable if a query call times out; missing or malformed rows are unsuccessful.
- A failed query command other than a timeout invalidates that call.

### Execution and file permissions

- The complete implementation under `/app` is transferred to a fresh environment.
- Your build command has 10,800 seconds.
- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.
- Include any additional dependencies needed at runtime under `/app`; development processes and packages installed elsewhere are not transferred.
- Aim to rank the relevant pages as highly as possible on new questions across all supplied domains and languages.

### Build interface

Provide executable `/app/build.sh` and `/app/run.sh`. The build command prepares the index and returns when it is ready:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /work/index
```

### Query interface

The query command accepts a JSONL file and writes a JSONL result file:

```bash
/app/run.sh \
  --index-dir /work/index \
  --queries /path/to/questions.jsonl \
  --output /path/to/results.jsonl
```

Honor the passed paths.

### Input and output contract

Each question has `query_id`, `question`, `domain` and `language`. Search the complete page collection for that domain. For every input question, return one object with its unchanged `query_id` and `results`, containing up to ten distinct pages in relevance order. Each result contains `page_id` and a finite numeric `score`; scores must be nonincreasing. Return page IDs from the requested domain. No answer or bounding box is required.

## Available Validation Data

The collection is in `/task/data/corpus`. Each line of `records.jsonl` describes a page with `page_id`, `domain`, `doc_id`, `image_path`, `width`, `height`, `markdown` and `page_number_in_doc`. Image paths are relative to the collection directory. The Markdown is a supplied transcription; the original page images are also available. Questions may be in a different language from the document. Treat `/task` as read-only and place your implementation under `/app`.

Public questions and their page-relevance annotations are in `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Use these for development and self-checking. Additional questions and annotations are withheld.

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
4. **Search quality.** Raw quality is nDCG@10 with linear relevance gains, averaged within each domain and then equally across the eight domains. Missing or invalid query results remain in the denominator.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
