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
  --index-dir /path/to/index
```

Executable `build.sh` must return 0 within 3,600 seconds when its indexes and any background service are ready. Build-started services may persist into querying.

### Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Executable `run.sh` must return 0 and finish the entire query batch within 20 seconds. Evaluate the same frozen query order in five rounds, each starting with a fresh build, index directory and service processes. Clear submission-owned IPC and writable state between rounds; operating-system file caches are not flushed. Each build retains its 3,600-second deadline. Sort successful batches by elapsed time, place failed, late or invalid batches last, and break timing ties by round order. Score the rankings from the third batch in that ordering, never select a batch by retrieval quality.

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

Evaluate retrieval by mean NDCG@10 on held-out queries. A failed build, fewer than three successful query batches, or a failed integrity audit receives zero credit. The single audit's aggregate, raw decision and normalized criterion value must agree; missing or inconsistent audit details produce zero and a nonzero verifier exit. A consistent rejection is a valid zero.

## Hidden Test Overview

The agent receives the rewritten instruction, public corpus, examples, model and resource documents. Held-out queries and labels are separate.

## Environment and available resources

A model is provided at `/task/models/Qwen3-Embedding-0.6B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted models and APIs, retrieval-integrity restrictions, endpoint/credential rules and usage restrictions.

## Author-only Notes

At the user's request, the agent-facing instruction omits annotation guidance, training-label quality commentary, batching/development suggestions and reward-normalization details. The frozen relevance judgments and baseline-normalized scorer are unchanged; their definitions remain in README.md and the verifier. This is an intentional exception to copying all author-side scoring details into the request.
