# Task: 1-1

## Task Description

Build an executable retrieval system over the supplied document corpus. Given a natural-language query, the system should retrieve and rank the most relevant corpus documents.

The objective is to maximize retrieval quality on held-out queries while satisfying the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Use the supplied document corpus and task data for retrieval. You may use only the external models and services explicitly permitted in `/task/docs/available_resources.md`; do not use an external search engine, external retrieval service, external datasets containing evaluation results, or precomputed query-to-result mappings.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the installed runtime, available packages, permitted models and services, credential handling rules, and resource restrictions.
- `build.sh` and `run.sh` must be executable files under `/app`.
- During verification, `/app` is read-only and the submission runs as a non-root user. Only the supplied `--index-dir` is writable for persistent and runtime-generated artifacts.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

## Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

`build.sh` must build all required local index and runtime artifacts and return exit status `0` when they are ready. It may prepare a background service if useful, but it must not require the verifier to keep a foreground process alive; `build.sh` must return successfully before the verifier invokes `run.sh`.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Do not require the verifier to know any additional fixed paths.

## Query interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
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

1. **Retrieval integrity.** The submission must implement a genuine retrieval system over the supplied corpus. It must not obtain relevance judgments or results through hidden labels, hard-coded query-to-document mappings, precomputed answer files, external datasets containing evaluation judgments, or unauthorized retrieval services. The explicitly permitted resources in `available_resources.md` may be used only according to their documented retrieval or query-transformation roles.
2. **Resource compliance.** The submission may use only the resources explicitly permitted in `/task/docs/available_resources.md` and must comply with all associated model, provider, endpoint, credential, and usage restrictions.
3. **Executable and output validity.** The verifier checks that `build.sh` and `run.sh` exist and are executable, invokes them through the specified interfaces, and validates the JSONL output structure, query coverage, result count, duplicate handling, document IDs, scores, and ranking order. Invalid output or a failed executable gate receives a score of `0`.
4. **Final retrieval score.** The submission must pass all hidden queries. For every hidden query, at least one relevant document must appear in the top three results. If any hidden query fails, the submission receives a score of 0.

## Hidden Test Overview

The hidden evaluation contains held-out queries with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available retrieval and generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
