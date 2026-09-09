# Task: Task-2-1

## Task Description

Improve the supplied long-document reranking system. Given a query and its fixed BM25 Top-100 candidate documents, the system should rerank the candidates using the supplied local `/tast/model/bge-reranker-large` model.

The candidate set and reranker model are fixed. You may optimize the reranking pipeline, but may not replace or train the model or modify the supplied candidates.

The objective is to maximize retrieval quality on held-out queries while satisfying the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` and `/tests` as read-only.
- Use exactly the candidate documents supplied with each query. Do not add, remove, replace, or independently retrieve candidate documents.
- Use only the supplied local `BAAI/bge-reranker-large` model for learned relevance scoring. Do not replace, fine-tune, retrain, distill, quantize, or otherwise modify the model, tokenizer, or configuration.
- Do not use precomputed query-to-document mappings, hidden relevance information, external datasets containing evaluation labels, or external retrieval/reranking services.
- Read `/task/docs/environment.md` for the installed runtime, packages, system tools, and resource limits available in the container.
- `build.sh` and `run.sh` must be executable files under `/app`.
- During verification, `/app` is read-only and the submission runs as a non-root user. Only the supplied `--index-dir` is writable for persistent and runtime-generated artifacts.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

`build.sh` must prepare all required corpus, model, and runtime artifacts, start the reranking service, and return exit status `0` only after the system is ready to process queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent preprocessing, cache, and other runtime artifacts. Do not require the verifier to know any additional fixed paths.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

Each query contains a fixed BM25 Top-100 candidate set. `run.sh` must rerank only the candidates supplied with that query and write exactly one result object for each input query.

It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- results must contain exactly five items when invoked with `--top-k 5`;
- every result must contain a `doc_id` identifying one of the candidate documents supplied with that query and a finite numeric `score`;
- document IDs must be unique within a query;
- results must be ordered from highest to lowest score; and
- equal-score results must use the original candidate order as the tie-break.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the full corpus.
- `/task/data/validation/queries.jsonl` — public development queries. Each record follows the same schema used by hidden queries.
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

1. **Reranking integrity.** The submission must implement a genuine reranking pipeline over the candidate documents supplied with each query. It must not obtain relevance judgments or results through hidden labels, hard-coded query-to-document mappings, precomputed answer files, external datasets containing the evaluation judgments, or external retrieval/reranking services.
2. **Candidate-set and model compliance.** The submission must rerank only the fixed BM25 Top-100 candidates supplied with each query and must use the supplied local `/tast/model/bge-reranker-large` model without replacing, training, or modifying it.
3. **Executable and output validity.** The verifier checks that build.sh and run.sh exist and are executable, invokes build.sh, waits for it to return successfully, and then invokes run.sh for the hidden queries. It also checks the JSONL result structure, query coverage, result count, duplicate handling, candidate document IDs, scores, and ranking output. Invalid output or a failed executable gate receives a zero score.
4. **Final retrieval score.** For a valid submission, the final task score is calculated only with `Accuracy@5`:

```text
score = 100 * average(Accuracy@5)
```

For an individual query, `Accuracy@5` is `1` when at least one relevant corpus document appears in the first five returned results, and `0` otherwise.

## Hidden Test Overview

The hidden evaluation contains held-out financial queries with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.

These documents are part of the Agent-visible task data and should be treated as read-only.