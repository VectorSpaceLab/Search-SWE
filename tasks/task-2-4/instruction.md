# Task: 2-4

## Task Description

Optimize the supplied ReAct retrieval starter over the corpus. Given a multi-constraint question, the system must return exactly five distinct corpus documents that best address its combined information need.

The objective is to maximize Gold Recall@5 on held-out questions. The starter is installed under `/app/starter`, with executable `/app/build.sh` and `/app/run.sh` entry points. You may modify or replace its retrieval and reasoning components while preserving the interfaces and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- `build.sh` must complete within 600 seconds.
- Each query may use at most 20 retrieval rounds. One search action returning a candidate set counts as one round; batched independent searches count separately.
- There is no per-query time limit. The shared 15,300-second execution budget and 15,600-second verifier phase limit still apply.
- The search service and `run.sh` must support up to five concurrent query invocations sharing the same `--index-dir`, with separate input and output files.
- Retrieve documents from the supplied corpus. Do not use hidden relevance labels, hard-coded evaluation query-to-document mappings, or external datasets/services containing evaluation answers or relevance labels. Public validation labels may be used for development and tuning.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- Read `/task/docs/available_resources.md` for optional external retrieval and generative resources, runtime credential handling, exact model allowlists, API restrictions, and jailbreak penalties.
- `build.sh` and `run.sh` must be executable files under `/app`.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.


### Starter

Read `/app/starter/README.md`. The baseline builds a SQLite FTS5/BM25 index, starts a shared search service, and uses a ReAct loop to search, observe documents, and select five IDs. With `OPENROUTER_API_KEY`, it uses an allowed generation model; without a key, it runs a single lexical search. Improve document coverage, retrieval, planning, or selection to increase Gold Recall@5.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Do not require the verifier to know any additional fixed paths.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

`run.sh` must process every supplied query and write exactly one result object for each input query. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

The verifier runs `build.sh` once, then invokes `run.sh` once per hidden query with up to five invocations in parallel. All invocations share the task's CPU, memory, index, and service resources.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"example-1","doc_ids":["100","101","102","103","104"]}
```

For every valid query:

- `query_id` must be a string preserving the identifier of the corresponding input query;
- `doc_ids` must be a JSON array containing exactly five non-empty strings;
- all five IDs must be distinct and match actual `docid` values in `/task/data/corpus.jsonl`;
- the list represents the system's final five selected documents, including when retrieval uses multiple internal rounds; and
- exactly one output record must be emitted for each input query, with no missing, duplicate, or extra query IDs.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.jsonl` — the full corpus.
- `/task/data/validation/queries.jsonl` — 20 public development queries. Each record follows the same schema used by hidden queries.
- `/task/data/validation/qrels_gold.txt` — public gold document relevance labels in TREC format: `query_id 0 docid 1`.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files under `/app`.

```text
/app/
├── build.sh          # executable build and service-start entry point
├── run.sh            # executable query entry point
├── starter/          # supplied ReAct baseline; may be modified or replaced
├── src/              # optional implementation modules
└── README.md         # optional implementation notes and self-test details
```

## Verification

After the Agent phase, Harbor transfers `/app` to a separate verifier with the same runtime and the private test split. `build.sh` must restart the service. The verifier checks the following items:

1. **Retrieval integrity.** Retrieve documents from the supplied corpus. Do not use hidden relevance labels, hard-coded evaluation query-to-document mappings, or unauthorized datasets or services.
2. **Resource compliance.** Follow the resource, model, provider, and usage restrictions in `/task/docs/available_resources.md`, including the build time, shared time budget, and 20-round retrieval limit stated in Requirements.
3. **Executable and output validity.** `build.sh` and `run.sh` must be executable and follow the specified interfaces. Each query must produce exactly one result containing five distinct, valid corpus document IDs. Failed execution or invalid output receives a score of `0` for the entire submission.
4. **Final retrieval score.** The only metric is Gold Recall@5, averaged equally across all hidden queries. For query `q`, let `R_q` be its five returned document IDs and `G_q` its gold document IDs:

```text
GoldRecall@5(q) = |R_q intersect G_q| / |G_q|
reward = mean_q GoldRecall@5(q)
score = 100 * reward
```

## Hidden Test Overview

The hidden evaluation contains 20 held-out questions with private gold document relevance labels. Hidden questions and their gold document IDs are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available retrieval and generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
