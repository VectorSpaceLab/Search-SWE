# Financial-Report Evidence Retrieval

## Task Description

Analysts need to check the figures behind financial questions across a shared collection of annual reports. They know what they want to investigate, but may not know which report contains the information. Build a reusable search system that finds the relevant reports and returns the original passages supporting each question, so the figures can be checked in context.

## Requirements

### Resource limits and workload

- Development and checking have a two-hour budget, with eight CPU cores, 32 GiB RAM, 100 GiB working storage and no GPU.
- The system must handle workloads of up to 8,000 requests in two calls of at most 4,000 requests.
- Each call has its own 3,600-second allowance.
- Completed valid JSONL rows remain usable if a call times out; missing or invalid query results are unsuccessful.
- A command failure other than a timeout invalidates that call.
- The index must remain usable across repeated calls after one build.

### Execution and file permissions

- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Provide executable `/app/build.sh` and `/app/run.sh`, together with any supporting files under `/app`. Build the shared collection once with:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /path/to/index
```

The command must finish successfully within 1,800 seconds and prepare everything needed for subsequent queries after a fresh start.

### Query interface

Then support repeated calls to:

```bash
/app/run.sh \
  --index-dir DIR \
  --queries JSONL \
  --output JSONL
```

Honor the supplied paths.

### Input and output contract

Each input row contains `query_id` and `question`. A target report identifier is not supplied. For each query, write one JSONL row containing exactly `query_id` and `spans`, with the same query identifier. The `spans` array may contain up to five evidence locations, ordered from most to least relevant. Each location contains exactly `document_id`, `start` and `end`. Use a report identifier from the supplied collection and integer Unicode-character offsets into that report's original `text`: `start` is inclusive, `end` is exclusive, and `0 <= start < end <= len(text)`. Each span may contain at most 512 Unicode characters. Find the passages that cover the supporting facts, preserving their original report and positions. An empty list is permitted when the system finds no evidence.

## Available Validation Data

The complete collection is in `/task/data/corpus/reports.jsonl`. Each row contains a `document_id` and the report's full `text`; all 885 reports are available. Example questions and their annotated evidence locations are in `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Use the supplied collection and examples to develop and check the system. Treat `/task` as read-only and put the implementation under `/app`.

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
4. **Search quality.** Raw quality is EvidenceRecall@5, averaged equally across held-out questions. A reference fact is covered when returned spans from the correct report jointly cover at least one complete accepted location. Repeated hits on one fact do not add credit.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.

The documented OpenRouter and Jina APIs are available under their provider, model and endpoint restrictions. Use the supplied reports and permitted resources, and leave all files required by the build and query commands under `/app`.
