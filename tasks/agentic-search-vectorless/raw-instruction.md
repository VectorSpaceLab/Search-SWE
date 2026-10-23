# Task: agentic-search-vectorless

## Task Description

Implement a retrieval system over the corpus. Given a multi-constraint question, return exactly five distinct corpus documents that best address its combined information need.

The objective is to maximize Gold Recall@5 on held-out questions. No starter, index, or entry points are supplied; implement them under `/app`.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- `build.sh` must complete within 600 seconds.
- Each query may use at most 20 retrieval rounds. One search action returning a candidate set counts as one round; batched independent searches count separately.
- Do not use embeddings (local, API, or precomputed) or BM25, including its variants and library/database implementations, at build time or query time. Do not use external retrieval or reranking services. The implementation approach is otherwise your choice, subject to the interfaces and resource restrictions.
- There is no per-query time limit. Build, query execution, and scoring share a 15,300-second wall-clock execution budget, including the 600-second build cap. The verifier phase allows 19,200 seconds in total, including a separate compliance audit of up to 3,600 seconds.
- The search service and `run.sh` must support up to five concurrent query invocations sharing the same `--index-dir`, with separate input and output files.
- Retrieve documents from the supplied corpus. Do not use hidden relevance labels, hard-coded evaluation query-to-document mappings, or external datasets/services containing evaluation answers or relevance labels. Public validation labels may be used for development and tuning.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- Read `/task/docs/available_resources.md` for optional generative resources, runtime credential handling, exact model allowlists, API restrictions, and jailbreak penalties.
- `build.sh` and `run.sh` must be executable files under `/app`.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.
- Resources are 32 CPUs, 16 GiB RAM, 200 GiB storage, and no GPU.


### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

`build.sh` must prepare any required corpus representation and runtime artifacts and return `0` only when search is ready. A service is optional; if started, it must remain available across repeated `run.sh` calls.

The verifier discards an agent-phase `/app/index` before build, so build must reconstruct the search artifacts from the supplied corpus.

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

Each input line is a JSON object with a string `query_id` and a non-empty string `question`, for example `{"query_id":"example-1","question":"Find documents satisfying these constraints."}`. The corpus document identifier field is `docid`.

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
├── src/              # optional implementation modules
└── README.md         # optional implementation notes and self-test details
```

## Verification

After the Agent phase, Harbor transfers `/app` to a separate verifier with the same runtime and the private test split. `build.sh` must rebuild its search artifacts. The verifier checks the following items:

1. **Retrieval integrity.** Retrieve documents from the supplied corpus. Do not use hidden relevance labels, hard-coded evaluation query-to-document mappings, or unauthorized datasets or services.
2. **Resource compliance.** A mandatory trajectory and submitted-code audit checks the embedding/BM25 bans, external resource/model restrictions, 20-round retrieval limit, hidden-label access, and verifier manipulation. A detected violation sets the entire reward to zero. The audit does not prescribe a retrieval architecture or programming language and does not judge relevance. Missing, malformed, failed, or timed-out audit results also leave reward at zero.
3. **Executable and output validity.** `build.sh` and `run.sh` must be executable and follow the specified interfaces. Each query must produce exactly one result containing five distinct, valid corpus document IDs. Failed execution or invalid output receives a score of `0` for the entire submission.
4. **Final retrieval score.** For valid execution that passes the compliance audit, the only quality metric is Gold Recall@5, averaged equally across all hidden queries. For query `q`, let `R_q` be its five returned document IDs and `G_q` its gold document IDs:

```text
GoldRecall@5(q) = |R_q intersect G_q| / |G_q|
reward = mean_q GoldRecall@5(q) if the compliance audit passes, otherwise 0
score = 100 * reward
```

## Hidden Test Overview

The hidden evaluation contains 20 held-out questions with private gold document relevance labels. Hidden questions and their gold document IDs are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
