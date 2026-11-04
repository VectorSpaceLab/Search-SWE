# Scientific-Paper Question Answering

## Task Description

Build an executable retrieval-augmented question answering system over the supplied collection of scientific-paper PDFs. Given a scientific question, the system should return a concise answer together with the paper that support the answer.

The objective is to maximize answer correctness and source attribution quality on held-out questions. You may use any method that satisfies the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Do not use precomputed query-to-answer mappings or external datasets/services containing evaluation answers.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- Read `/task/docs/available_resources.md` for optional external retrieval and generative resources, runtime credential handling, exact model allowlists, API restrictions, and jailbreak penalties.
- `build.sh` and `run.sh` must be executable files under `/app`.
- `build.sh` must complete within 3600 seconds.
- Each query must complete within 900 seconds.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /app/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Use the supplied paths: the verifier's index and output directories may differ from these examples.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

`run.sh` must process every supplied query and write exactly one result object for each input query. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

The verifier runs `build.sh` once, then invokes `run.sh` once per hidden query with up to five invocations in parallel. A query's time limit starts when its `run.sh` process starts; time waiting for an available slot is excluded. All invocations share the task's CPU, memory, index, and service resources.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","answer":"The answer for the query","evidence":"document-id"}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- `answer` must directly answer the question, contain non-whitespace text, and be at most 20,000 characters after JSON decoding, including all whitespace;
- every result must contain a `answer` for the query and a `evidence` identifying the document for the answer from the supplied corpus.
- `evidence` must be the PDF filename with the `.pdf` extension removed, e.g. `document-id.pdf` → `document-id`.

Each per-query output must be a regular file of at most 64 MiB; the combined results must also fit within 64 MiB. An over-length answer or oversized output invalidates the entire submission and gives score `0`.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus` — the collection of 300 scientific-paper PDFs.
- `/task/data/validation/queries.jsonl` — public development queries. Each record follows the same schema used by hidden queries.
- `/task/data/validation/golden_answers.jsonl` — reference answers and evidence document IDs for the public queries.

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

After the Agent phase, Harbor transfers `/app` to a separate verifier with the same runtime and the private test split. `build.sh` must restart the service. The verifier checks the following items:

1. **Retrieval and answer integrity.** Answer questions using the supplied PDFs. Do not use hidden labels, hard-coded evaluation answers, or unauthorized datasets or services.
2. **Resource compliance.** Follow `/task/docs/available_resources.md`. The verifier allows 3,600 seconds for `build.sh` and 900 seconds per query, running up to five queries concurrently.
3. **Executable and output validity.** `build.sh` and `run.sh` must be executable and follow the specified interfaces. Each query must produce exactly one result with its `query_id`, an `answer` satisfying the output contract's content and length requirements, and a valid corpus document ID in `evidence`. Failed execution or invalid output, including exceeding the answer or file-size limits, receives a score of `0` for the entire submission.
4. **Final answer score.** The metric is LLMJudgeAccuracy, averaged equally across all hidden queries. A query earns credit only when its evidence document matches the reference and the LLM judge accepts its answer as semantically equivalent to the reference answer.

```text
LLMJudgeAccuracy(q) = evidence_match(q) * semantic_answer_credit(q)
reward = mean_q LLMJudgeAccuracy(q)
score = 100 * reward
```

An independent trajectory audit checks compliance with the task and resource restrictions. A failed audit sets the entire submission's reward and score to `0`.

## Hidden Test Overview

The hidden evaluation contains held-out queries with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available retrieval and generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are read-only task data. API use is optional; follow the resource permissions, usage restrictions and credential-handling rules in `available_resources.md`.
