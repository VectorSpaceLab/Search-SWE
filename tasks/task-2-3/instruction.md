# Task: Task-2-3

## Task Description

Build a query-side retrieval system for the supplied fixed document vectors. The query encoder must be based on the provided 0.6B backbone. Maximize held-out Accuracy@1 while meeting the fixed runtime gate.

## Requirements

- Treat /task as read-only and place the complete submission under /app/submission.
- The Agent phase has a 12-hour time limit. Task-specific submission verification has a 70-minute time limit, excluding the separate integrity judge. If the Agent phase, task-specific verification, or integrity judge times out, the score is 0.
- Base the query-side system on /task/models/Qwen3-Embedding-0.6B.
- Use the vectors passed through --doc-vectors without modifying, replacing, re-encoding, or reordering them.
- Preserve the row correspondence between /task/data/doc.npy and /task/data/corpus.jsonl.
- Make the submission self-contained and able to run without network access.
- Do not use hidden data, hard-coded query-to-document mappings, precomputed answers, or external retrieval, reranking, generation, or answer services.

The verifier invokes:

~~~bash
/app/submission/run.sh --doc-vectors /task/data/doc.npy --queries /path/to/queries.jsonl --output /path/to/results.jsonl --top-k 1
~~~

run.sh must be executable, process every query once in input order, write deterministic results, exit successfully, and leave no background processes.

Each output line must have this form:

~~~json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
~~~

For --top-k 1, return exactly one corpus document with a finite numeric score. Sort by descending score and use corpus order to break ties.

## Available Validation Data

The fixed document vectors, corpus mapping, and public validation split are under /task/data. The supplied query backbone and reference starter model are under /task/models.

## Environment and Available Resources

Read /task/docs/environment.md and /task/docs/available_resources.md. Agent-stage network access is available, but the submitted system must not depend on it.

## Expected Artifacts

Submit an executable entry point and all required local files:

~~~text
/app/submission/
├── run.sh
└── ...
~~~

The verifier copies only /app/submission.

## Verification

The verifier runs the fixed reference starter and the submission on the same private queries and document vectors. Submissions that meet the fixed runtime gate are evaluated by held-out Accuracy@1. The verifier also checks vector integrity, output format, determinism, and background processes.

## Hidden Test Overview

The hidden split contains held-out retrieval queries and private relevance labels disjoint from the public validation split. Hidden data is unavailable during the Agent phase.
