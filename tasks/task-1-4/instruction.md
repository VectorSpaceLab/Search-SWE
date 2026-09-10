# Task: Task-1-4

## Task Description

Build an executable evidence-localization system over the supplied collection of long PDF documents. Given a natural-language query and a target PDF, the system should return the locations within that PDF that best contain the relevant evidence.

The objective is to maximize evidence-localization quality on held-out queries. You may use any retrieval architecture that satisfies the executable interface and resource constraints.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Do not use precomputed query-to-answer mappings or external datasets/services containing evaluation answers.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools available in the container.
- Read `/task/docs/available_resources.md` for optional external retrieval and generative resources, runtime credential handling, exact model allowlists, API restrictions, and jailbreak penalties.
- `build.sh` and `run.sh` must be executable files under `/app`.
- `page` is the 1-based physical page index of the target PDF.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /app/index
```

`build.sh` must build all required index and runtime artifacts, start the search service, and return exit status `0` only after the service is ready to accept queries. The service must remain available across repeated `run.sh` calls.

The `--index-dir` argument is the location for persistent indexes and other build artifacts. Use the supplied paths: in verification, `--corpus` points to a different collection of held-out PDFs, and the index and output directories may differ from these examples.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

`run.sh` must process every supplied query and write exactly one result object for each input query. It may use any internal protocol or service endpoint, as long as it works with the `build.sh` process and the command-line interface.

### Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"page":12,"evidence":"supporting text from the page","score":0.123}]}
```

For every valid query:

- `query_id` must preserve the identifier of the corresponding input query;
- `results` must contain exactly five items when invoked with `--top-k 5`;
- every result must contain a valid `page` from the query's target PDF, a non-empty `evidence` string from that page, and a finite numeric `score`;
- returned pages must be unique within a query;
- results must be ordered from highest to lowest score; and
- equal-score results must use ascending page order as the tie-break

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus` — six public development PDFs.
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

After the Agent phase, Harbor transfers `/app` to a fresh verifier environment with the same runtime. The verifier provides six held-out PDFs and 30 private queries; public validation data is not mounted. `build.sh` must restart the service because Agent-phase processes are not transferred. Submission commands run as an unprivileged user; evaluation-time dependencies must be available in the base image or installed under `/app`.

The verifier allows 2,400 seconds for `build.sh` and 1,800 seconds for one `run.sh` invocation covering all hidden queries, within a 10,800-second verifier phase. It checks the following items:

1. **Evidence-localization integrity.** The submission must implement a genuine evidence-localization pipeline over the supplied target PDFs. It must not obtain relevance judgments or evidence locations through hidden labels, hard-coded query-to-location mappings, precomputed answer files, external datasets containing the evaluation judgments, or external search/answer services.
2. **Executable and service behavior.** The verifier checks that `build.sh` and `run.sh` exist and are executable, invokes `build.sh`, waits for it to return successfully, and then invokes `run.sh` for the hidden queries.
3. **Output validity.** The verifier checks the JSONL result structure, query coverage, result count, page numbers, evidence fields, scores, duplicate handling, and ranking output. Each returned location must belong to the query's target PDF, and the returned evidence must correspond to text on the reported page. Invalid output or a failed executable gate receives a zero score.
4. **Final localization score.** Page relevance is scored deterministically against the gold labels; no model judges answer correctness. The model-based audit checks only trajectory compliance. For a valid submission that passes the audit, the final task score is calculated only with `Recall@5`:

```text
score = 100 * average(Recall@5)
```

For an individual query, `Recall@5` is the fraction of relevant evidence pages that appear among the first five returned locations:

```text
Recall@5 = (# relevant evidence pages retrieved in the top 5) / (# relevant evidence pages for the query)
```

## Hidden Test Overview

The hidden evaluation contains 30 held-out long-document queries with private relevance judgments. Its target PDFs and queries differ from the public development examples and are not copied into the Agent-visible environment. Query IDs are local to each split and may be reused across splits.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the available retrieval and generative API resources, runtime environment-variable handling, model allowlist, provider and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
