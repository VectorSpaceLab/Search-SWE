# Methodology Inspiration Retrieval

## Task Description

Build an executable retrieval system that returns papers offering methodological
inspiration for a scientific proposal's problem and motivation. Topic similarity
alone is insufficient. Evaluate quality using mean Recall@3 on hidden queries;
higher retrieval quality improves the final score.

## Requirements

- Runtime and resource restrictions: `/task/docs/environment.md` and
  `/task/docs/available_resources.md`; both are part of the task contract.
- Use only supplied task material and permitted APIs. No external papers,
  datasets, additional weights, benchmark answers, hidden judgments, external
  search services or hard-coded query-to-result mappings. Do not expose
  credentials in source, logs or artifacts.
- Create the complete submission under `/app`, including executable `build.sh`
  and `run.sh` and runtime dependencies.
- Development has six hours.
- The separate verifier transfers submission files, not installed packages or
  live processes. It runs the submission as non-root with `/app` and `/task`
  read-only. Corpus, model and resource docs remain available; examples do not.
  Write generated files to the supplied index directory and results to the
  requested output path.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

Indexing and all initialization, including any resident service, must finish
with exit status zero within 1,200 seconds. The index starts empty and its path
may vary. Hidden queries are provided only after build succeeds.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 3
```

Each input has `query_id` and `text`. The complete invocation must finish with
exit status zero within 12 seconds, including API waiting and output writing.

### Output contract

Write one UTF-8 JSONL record per query, preserving the input ID, in any query order:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

Cover all queries exactly once. Return at most three distinct corpus IDs, with
finite numeric scores in descending order and corpus-order ties. Empty lists
are valid.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the full paper corpus.
- `/task/data/examples.jsonl` — labeled examples.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files
and all runtime dependencies under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable query entry point
└── ...               # supporting implementation files and dependencies
```

## Verification

Retrieval quality is evaluated using mean Recall@3 on hidden queries; higher
retrieval quality improves the final score. Build/query timeouts, command
failures, invalid output and integrity violations give score zero.

## Hidden Test Overview

The hidden evaluation uses scientific proposals with private relevance
judgments. Hidden queries are provided only after build succeeds. The public
examples are not available in the separate verifier.

## Environment and available resources

The runtime provides one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and
100 GiB storage. The local model is `/task/models/stella_en_400M_v5`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted APIs, model/provider/endpoint restrictions and credential handling.
