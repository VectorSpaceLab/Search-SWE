# Legal Stance Retrieval

## Task Description

Build an executable search system over the supplied court cases. Inputs contain a legal `query` and requested `stance`: `supported`, `refuted`, or `all`. Retrieve supporting cases, contradicting cases, or either kind respectively. `all` does not require both kinds to exist.

## Requirements

- Read `/task/docs/environment.md` and `/task/docs/available_resources.md` and obey the documented model, endpoint, credential and usage restrictions.
- Model/API permissions and retrieval-integrity restrictions are documented in the resource document.
- Agent phase: 6 hours. Save all submission artifacts under `/app`. `/task` is read-only.
- `build.sh` and `run.sh` must be executable files under `/app`.
- Separate verifier transfers `/app` and the trajectory, with fixed corpus and model mounts. Agent services and public examples are not transferred. Persist all required artifacts under `/app`.
- Verification runs submission code as non-root with `/app` read-only. Use `--index-dir` for caches/runtime artifacts and `--output` for results.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

Executable `build.sh` must return 0 within 3,600 seconds when its indexes and any background service are ready. Build-started services may persist into querying.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Executable `run.sh` must return 0 and finish the entire query batch within 20 seconds.

### Output contract

Write one JSONL row per input query:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

Preserve query IDs. Each results array must contain exactly ten distinct known corpus document IDs with finite numeric scores in non-increasing order. Equal-score order is unrestricted. Array order determines rank.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the full court-case corpus.
- `/task/data/examples` — public development examples.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files and all required artifacts under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable batch-query entry point
└── ...               # supporting implementation files and artifacts
```

## Verification

Evaluate retrieval by mean NDCG@10 on held-out queries. Failed or late commands, invalid output or a failed integrity audit receive zero credit.

## Hidden Test Overview

The agent receives the rewritten instruction, public corpus, examples, model and resource documents. Held-out queries and labels are separate.

## Environment and available resources

A model is provided at `/task/models/Qwen3-Embedding-0.6B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted models and APIs, retrieval-integrity restrictions, endpoint/credential rules and usage restrictions.

## Author-only Notes

At the user's request, the agent-facing instruction omits annotation guidance, training-label quality commentary, batching/development suggestions and reward-normalization details. The frozen relevance judgments and baseline-normalized scorer are unchanged; their definitions remain in README.md and the verifier. This is an intentional exception to copying all author-side scoring details into the request.
