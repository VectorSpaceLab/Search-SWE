# ChunQiu Temporal Retrieval

## Task Description

Build an executable system to retrieve original event records from Classical
Chinese annals for a requested reign, year, month or time window. Rank event
records and distinguish them from later commentary discussing the same period.
Return up to ten corpus documents per query.

## Requirements

- Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for
  the runtime and complete model/provider/endpoint policy.
- Only the documented APIs are permitted, for the supplied task material.
- No hidden questions/judgments, external datasets/documents, external search or
  additional pretrained weights. No precomputed or hard-coded query-to-answer
  mappings. Keep credentials out of source, logs and artifacts.
- The development budget is 6 hours.
- Submit executable `/app/build.sh`, `/app/run.sh`, and all runtime dependencies
  under `/app`. Installed packages and live development processes are not
  transferred. `/task` is read-only.
- Verification uses a separate environment and an unprivileged user, with
  `/app` read-only. The corpus, model and docs remain available; neither examples
  file is mounted there. Use the supplied index directory for generated files
  and the requested output path for results; do not require another fixed
  writable path.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

The actual index path may vary and starts empty. Complete indexing and all
initialization, including any resident service, and exit zero within 1,200
seconds. Query inputs are supplied only after successful initialization.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Read `query_id` and `text` from each query.

The verifier submits the complete hidden query batch in one invocation.
Batching is allowed. Finish with exit status zero within 120 seconds, including
input processing, encoding, retrieval, reranking, API waiting and output writing.

### Output contract

Write exactly one UTF-8 JSONL result per query, preserving its ID, in any query
order:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

Return zero to ten distinct corpus IDs with finite numeric scores, sorted by
descending score; ties follow corpus order. Empty lists are valid.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the full corpus.
- `/task/data/examples.jsonl` — labeled examples.
- `/task/data/dated_examples.jsonl` — dated corpus examples.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files
and all runtime dependencies under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable batch-query entry point
└── ...               # supporting implementation files and dependencies
```

## Verification

Maximize mean nDCG@10 on the hidden test set. Build or batch timeouts, command
failures, missing or invalid output, or integrity violations give score zero.

## Hidden Test Overview

The hidden queries and judgments are unavailable during development. Query
inputs are supplied as a complete batch only after successful initialization;
neither public examples file is mounted in the verifier.

## Environment and available resources

The runtime provides one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and
100 GiB storage. The local model is `/task/models/Qwen3-Embedding-0.6B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the complete model/provider/endpoint policy and credential rules.
