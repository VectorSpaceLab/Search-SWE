# Code Context Retrieval

## Task Description

Implement a reusable search engine that locates source regions needed to understand and address an issue in its supplied repository snapshot. Retrieve reading context; generating a patch is not required. The objective is high line F1 on held-out issues.

Queries contain `query_id`, `snapshot_id` and `text`. Only files in that snapshot are eligible.

## Requirements

- Put implementation and dependencies under `/app`; `/task` is read-only. The entire `/app` transfers to a fresh verifier. Agent-installed global dependencies and running processes do not transfer.
- Submit executable `/app/build.sh` and `/app/run.sh`.
- In the verifier, commands run unprivileged, `/app` is read-only except the provided index directory, and query output must be written to the supplied output path.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. Only the documented retrieval and generative APIs are permitted. No external repository, issue, patch, answer or label lookup; no hard-coded evaluation mappings, hidden-file access or grading manipulation. Credentials must not be included in submitted files or artifacts.
- The development budget is 2 hours.

### Build interface

The verifier builds once, within 3,600 seconds, including any service startup:

```bash
/app/build.sh \
  --corpus /task/data/repos \
  --index-dir /app/index
```

The verifier supplies a fresh index directory and requires successful build exit. Keep generated runtime files there. Services started during build may remain running; build must return when ready.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

Process all input queries and produce exactly one JSONL result per query. Private evaluation invokes one query at a time, with concurrency 1. Each invocation has 180 seconds including startup, API calls and output writing.

### Output contract

A result has exactly `query_id` and `regions`; each region has exactly `path`, `start`, `end`:

```json
{"query_id":"query-id","regions":[{"path":"src/example.py","start":20,"end":55}]}
```

Preserve the input query ID. Return zero to five regions and at most 500 distinct source lines in total. Paths are repository-relative; line numbers are integers, one-based and inclusive, within actual file bounds. Physical newlines delimit lines; a final newline does not add an empty line. Overlapping ranges count once; ordering does not affect quality. An empty region list scores zero.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/repos/<snapshot_id>/` — the source corpus, one directory per snapshot.
- `/task/data/validation/queries.jsonl` — public development queries.
- `/task/data/validation/ground_truth.jsonl` — reference source regions for the public queries.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files and all required implementation code and dependencies under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable query entry point
└── ...               # supporting implementation files and dependencies
```

## Verification

Single-query quality is line F1: `2 * matched_lines / (returned_lines + reference_lines)`, where lines match by file path and line number within the query's snapshot. The final quality score is the mean on hidden queries. Missing, malformed, invalid, failed or timed-out query outputs score zero for that query. Build failure or confirmed integrity violation scores zero overall.

## Hidden Test Overview

The hidden evaluation uses held-out issues with private reference source regions. Each query identifies the repository snapshot eligible for retrieval, using the same input and output schemas as public development queries.

## Environment and available resources

The runtime provides 16 CPU cores, 32 GiB RAM and 100 GiB storage, with no GPU.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted retrieval and generative APIs, provider/model restrictions and credential handling.
