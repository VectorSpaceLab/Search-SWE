# Task: Task-1-4

## Task Description

Build an executable evidence-localization system over the supplied single long PDF. Given a natural-language query, the system should return the physical pages within that PDF that best contain the relevant evidence.

The objective is to maximize evidence-localization quality on held-out queries. You may use any retrieval architecture that satisfies the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Do not use precomputed query-to-answer mappings or external datasets/services containing evaluation answers.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- Read `/task/docs/available_resources.md` for optional external retrieval and generative resources, runtime credential handling, exact model allowlists, API restrictions, and jailbreak penalties.
- `build.sh` and `run.sh` must be executable files under `/app`.
- `page` is the 1-based physical page index of the supplied PDF.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /app/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Use the supplied paths: verification uses the same PDF at a different mount location, and the index and output directories may differ from these examples. The corpus directory contains exactly one PDF.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

Each input line has the following schema. Query IDs are opaque identifiers; all queries refer to the sole PDF, so no `target` field is supplied.

```json
{"query_id":"opaque-query-id","query":"Describe the passage to locate."}
```

`run.sh` must process every supplied query and write exactly one result object for each input query. The verifier invokes it separately for each query, with up to five concurrent processes sharing the index and any build-started service. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"page":12,"evidence":"text from page 12","score":0.9},{"page":13,"evidence":"text from page 13","score":0.8},{"page":25,"evidence":"text from page 25","score":0.7},{"page":26,"evidence":"text from page 26","score":0.6},{"page":30,"evidence":"text from page 30","score":0.5}]}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- `results` must contain exactly five items when invoked with `--top-k 5`;
- every result must contain a valid `page` from the supplied PDF, a non-empty `evidence` string from that page, and a finite numeric `score`;
- returned pages must be unique within a query;
- results must be ordered from highest to lowest score; and
- equal-score results must use ascending page order as the tie-break.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus` — the single long PDF used for both development and hidden evaluation.
- `/task/data/validation/queries.jsonl` — public development queries. Each record follows the same schema used by hidden queries.
- `/task/data/validation/golden_answers.jsonl` — reference physical pages and supporting excerpts for the public queries.

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

After the Agent phase, Harbor transfers `/app` to a fresh verifier environment with the same runtime. The verifier provides the same PDF and private queries; public validation queries and labels are not mounted. `build.sh` must restart the service because Agent-phase processes are not transferred. Submission commands run as an unprivileged user; evaluation-time dependencies must be available in the base image or installed under `/app`.

The verifier allows 2,400 seconds for `build.sh`. Each query runs in its own `run.sh` process with a 900-second limit and up to five processes running concurrently. All queries share a 1,800-second execution budget; unfinished or unlaunched queries at that deadline score zero. Queuing does not consume a query's individual limit, but the shared deadline still applies. The runner has an additional 60 seconds for cleanup and result collection. These limits are within the 10,800-second verifier phase. It checks the following items:

1. **Evidence-localization integrity.** The submission must implement a genuine evidence-localization pipeline over the supplied PDF. It must not obtain relevance judgments or evidence locations through hidden labels, hard-coded query-to-location mappings, precomputed answer files, external datasets containing the evaluation judgments, or external search/answer services.
2. **Executable and service behavior.** The verifier checks that `build.sh` and `run.sh` exist and are executable, invokes `build.sh`, waits for it to return successfully, and then invokes `run.sh` for each hidden query. A failed or timed-out query scores zero while other queries continue. Failure to build the shared index or initialize verification prevents all queries from scoring.
3. **Output validity.** The verifier checks each query's JSONL result structure, result count, page numbers, evidence fields, scores, duplicate handling, and ranking output. Each returned location must belong to the supplied PDF, and the returned evidence must correspond to text on the reported page. A missing or invalid output scores zero for that query; it remains in the average's denominator.
4. **Final localization score.** Page relevance is scored deterministically against the gold labels; no model judges answer correctness. The model-based audit checks only trajectory compliance. For a valid submission that passes the audit, the final task score is calculated only with `Recall@5`:

```text
reward = average(Recall@5), with failed or invalid queries contributing zero
```

For an individual query, `Recall@5` is the fraction of relevant evidence pages that appear among the first five returned locations:

```text
Recall@5 = (# relevant evidence pages retrieved in the top 5) / (# relevant evidence pages for the query)
```

The reward is between 0 and 1. The evaluation report displays `score = 100 * average(Recall@5)` before the trajectory gate. A failed trajectory audit sets the final reward to zero.

## Hidden Test Overview

The hidden evaluation contains held-out queries with private page-relevance judgments over the same PDF. Hidden queries and labels differ from the public development examples and are not copied into the Agent-visible environment. Query IDs are independent opaque identifiers, unique across splits, and query order does not indicate page position.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available retrieval and generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
