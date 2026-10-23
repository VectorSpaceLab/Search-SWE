# Lightweight Query Retrieval

## Task Description

Process batches of search queries. Return up
to ten ranked documents from each query's specified collection, while meeting
a fixed retrieval-quality threshold and minimizing complete query-processing
time. Use the supplied resources; no particular implementation is required.

## Requirements

- Environment and resources: `/task/docs/environment.md` and
  `/task/docs/available_resources.md`.
- No network or external APIs. No external datasets, additional pretrained
  weights, hidden labels, precomputed test answers or hard-coded answer mappings.
- Six hours of development.
- Submit all required files under `/app`, including executable `build.sh` and
  `run.sh`. This directory transfers to the separate verifier. The harness also
  transfers the execution trajectory for a protected integrity audit.
- Development processes and installed packages do not transfer. Corpus, base
  model and resource documents remain available; examples do not.
- `/app` and `/task` are read-only. Use the index directory during build and
  `$TMPDIR` at runtime.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

Build into the initially empty index directory within 1,200 seconds and exit
zero. The index is read-only afterwards.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh --index-dir /path/to/index --serve
```

Service startup has 120 seconds and must emit exactly one readiness JSON line:

```json
{"status":"ready"}
```

Keep the process running and handle each following stdin JSON line with one
stdout JSON line. Logs go to stderr. Each request has this shape:

```json
{"queries":[{"query_id":"request-id","collection":"corpus1","text":"query text","instruction":"retrieval instruction"}],"top_k":10}
```

### Output contract

Each response line must be a JSON object with this shape:

```json
{"results":[{"query_id":"request-id","results":[{"doc_id":"document-id","score":1.0}]}]}
```

Cover every query exactly once, in any query order. Each document list contains
at most ten distinct, valid IDs from its query's collection, with finite numeric
scores in descending order. Ties may retain the returned order.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — 66,454 documents in three collections.
- `/task/data/examples.jsonl` — 80,000 labeled examples.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files
and all required runtime files under `/app`.

```text
/app/
├── build.sh          # executable index-build entry point
├── run.sh            # executable persistent-query entry point
└── ...               # supporting implementation files and dependencies
```

## Verification

Warm-up uses supplied example queries and has 60 seconds. Then all 1,271 hidden queries arrive in
one batch, which must complete within 120 seconds. Timing includes receiving
and processing queries, retrieval, ranking and returning the response. Build,
model loading and warm-up are excluded. Use three fresh service instances with
fresh temporary storage; aggregate by median retrieval time.

Quality is original graded nDCG@10, with relevance grades used directly as gains
and an equal mean across the three collections. Every timed run must reach
0.45. Below this threshold the score is zero. Valid submissions meeting this
requirement earn higher scores for lower median retrieval times. A median time
of 0.8 seconds or more earns zero.

Final reward requires the integrity audit to pass. The audit checks the execution
trajectory and submitted files against the resource, data and anti-hardcoding
rules above. An unavailable, failed or invalid audit yields zero. Normal
corpus-derived indexes, preprocessing and parameters trained using the supplied
resources are allowed; low retrieval quality or speed alone is not a violation.

## Hidden Test Overview

The hidden evaluation contains 1,271 queries across three collections. All
hidden queries arrive in one batch after service startup and warm-up. Hidden
labels are unavailable during development; the public examples file is not
available to the submitted system in the separate verifier.

## Environment and available resources

The runtime provides one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and
100 GiB storage. The base model is `/task/models/Llama-3.2-1B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local resources and the offline policy.
