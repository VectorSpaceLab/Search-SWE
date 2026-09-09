# Task: 1-2

## Task Description

Build an executable search system over the supplied vector corpus. Given a query vector, the system should retrieve and rank the most relevant corpus items.

The objective is to maximize retrieval quality on held-out queries under the evaluator's resource constraints. You may use any indexing, storage, and retrieval architecture that satisfies the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Use only the supplied precomputed vectors and task data for retrieval. Do not use external models, retrieval services, external datasets containing evaluation results, or precomputed query-to-result mappings.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- `build.sh` and `run.sh` must be executable files under `/app`.
- During verification, `/app` is read-only and the submission runs as a non-root user. Only the supplied `--index-dir` is writable for persistent and runtime-generated artifacts.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.
- The `build.sh` process must complete within 120 seconds, including index construction and service startup.
- Each per-query `/app/run.sh` invocation must complete within 0.5 seconds of end-to-end wall-clock time, measured from process start to exit. The verifier may invoke `/app/run.sh` separately for each query.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --vectors /task/data/vectors.f32 \
  --metadata /task/data/metadata.jsonl \
  --config /task/data/vector_config.json \
  --index-dir /app/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Do not require the verifier to know any additional fixed paths.

### Query interface

The verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --query-vectors /task/data/validation/query_vectors.f32 \
  --query-metadata /task/data/validation/query_metadata.jsonl \
  --query-config /task/data/validation/vector_config.json \
  --output /tmp/results.jsonl \
  --top-k 3
```

`run.sh` must process every supplied query and write exactly one result object for each input query. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- `results` must contain exactly three items when invoked with `--top-k 3`;
- every result must contain a `doc_id` identifying a document from the supplied corpus and a finite numeric `score`;
- document IDs must be unique within a query;
- results must be ordered from highest to lowest score; and
- equal-score results must use corpus order as the tie-break.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/vectors.f32` — 1,500,000 normalized float32 corpus vectors with dimension 1024.
- `/task/data/metadata.jsonl` — 1,500,000 metadata rows corresponding one-to-one with the corpus vectors.
- `/task/data/vector_config.json` — configuration for the corpus vector collection.
- `/task/data/validation/query_vectors.f32` — public development query vectors.
- `/task/data/validation/query_metadata.jsonl` — metadata corresponding to the public query vectors.
- `/task/data/validation/vector_config.json` — configuration for the public query vectors.
- `/task/data/validation/queries.jsonl` — public development query records.
- `/task/data/validation/ground_truth.jsonl` — normalized labels for the public queries.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files under `/app`.

```text
/app/
├── build.sh          # executable build and service-start entry point
├── run.sh            # executable query entry point
├── src/              # optional implementation modules
└── README.md         # optional implementation notes and self-test details
```

## Verification

After the Agent phase, the Harbor verifier runs the submission in the same task environment and uses the private test split. The verifier checks the following items:

1. **Retrieval integrity.** The submission must implement a genuine vector retrieval system over the supplied corpus vectors. It must not obtain relevance judgments or results through hidden labels, hard-coded query-to-document mappings, precomputed answer files, external datasets containing the evaluation judgments, or external retrieval services.
2. **Executable and runtime behavior.** The verifier checks that `build.sh` and `run.sh` exist and are executable. It invokes `build.sh` and requires it to complete successfully within 120 seconds, including index construction and service startup. It then invokes `run.sh` for the hidden query vectors and enforces the specified retrieval-latency limit.
3. **Output validity.** The verifier checks the JSONL result structure, query coverage, result count, duplicate handling, document IDs, scores, and ranking output. Invalid output or a failed executable gate receives a zero score.
4. **Final retrieval score.** The submission must pass all hidden queries. For every hidden query, at least one relevant document must appear in the top three results, and retrieval must complete within 0.5 seconds. If any hidden query fails either condition, the submission receives a score of 0.

## Hidden Test Overview

The hidden evaluation contains held-out query vectors with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.

These documents are part of the Agent-visible task data and should be treated as read-only.
