# Quantity-aware Retrieval

## Task Description

Build an executable clinical-passage retrieval system using MedQuant. Return at most ten corpus documents that address a natural-language query and its numerical condition, ranked by relevance.

## Requirements

- `/task/docs/environment.md` and `/task/docs/available_resources.md` are normative, read-only runtime/resource documentation.
- Follow the exact model/provider/endpoint policy in the resource documents. API use is restricted to the supplied task material. No external corpus, benchmark answers, hidden labels/questions, external datasets, search services, precomputed query-answer files, hard-coded query-answer mappings, or additional pretrained weights. Do not expose credentials in code/logs/artifacts.
- All submission files and runtime dependencies belong under `/app`; `/task` is read-only.
- In verification `/app` is read-only, execution uses an unprivileged user, and only the supplied index directory and requested result path are writable. Corpus/model/docs remain mounted; `examples.jsonl` does not. Agent-installed packages and live processes are not transferred.
- Submit executable `/app/build.sh` and `/app/run.sh`.
- Development has a 6-hour budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

The actual index path can differ and starts empty. Complete all initialization and exit 0 within 1,200 seconds. Query invocations begin only after a successful build. Do not require another fixed writable path.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Read `query_id` and `text` from each input query.

Each query has a 5-second time limit. A timeout scores zero for that query.

### Output contract

Produce exactly one UTF-8 JSONL object per query:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

Preserve the supplied query ID. Return 0–10 unique corpus IDs with finite numeric scores, descending by score and using corpus order for ties. Empty lists are valid.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the searchable collection.
- `/task/data/examples.jsonl` — labeled examples.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files and all runtime dependencies under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable query entry point
└── ...               # supporting implementation files and dependencies
```

## Verification

Retrieval quality is evaluated by mean nDCG@10 on a hidden test set. Maximize this metric to improve the final score.

Build failures, other execution errors, invalid output or integrity violations result in a task score of zero. Resource and model/provider/endpoint/credential restrictions apply throughout.

## Hidden Test Overview

The hidden test set contains queries with private relevance judgments. Hidden questions and labels are unavailable during development. The examples file is not mounted in the separate verifier.

## Environment and available resources

The runtime provides one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and 100 GiB storage. Read-only model files are available at `/task/models/Qwen3-Embedding-0.6B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted models and APIs, provider/endpoint restrictions and credential handling.
