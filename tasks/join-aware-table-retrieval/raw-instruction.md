# Join-Aware Table Retrieval

## Task Description

Build a reusable catalog search engine for analysts who know their business
question but do not know which tables contain the necessary information or how
those tables connect. Given a natural-language question, return candidate tables
and column-level joins that a downstream analyst or SQL system can use.

The objective is to maximize complete table-and-join coverage on held-out
questions. Choose the index representation and search method within the supplied
resources. SQL generation and executing the business query are outside scope.
Training is not required.

Authoring note: the user requests the presentation used by
`tasks/reasoning-query-rewriting/instruction.md`: a natural task request with
fenced Bash commands and JSON examples. State machine allocations and the coding
phase's time budget concisely. Keep internal process limits, catalog preparation
details and diagnostic reporting in author/runtime metadata.
Build, index, startup and query limits, interface fields, validity rules and
scoring remain explicit in the request.

## Requirements

- Implement the engine and its supporting code/resources under `/app/submission`.
  This directory starts empty; no retrieval implementation is supplied.
- Build retrieval state from the shared catalog. Questions do not identify their
  target database group; the entire catalog may be inspected and indexed before
  questions arrive.
- Implement general retrieval rather than hard-coded question-specific answers.
  Do not retrieve external Spider SQL or answers, inspect hidden grading files,
  or manipulate grading or reward files.
- Use only the supplied column-level relationships. Do not invent cross-group
  joins.
- Work within 16 CPU cores, 32 GiB RAM and 100 GiB storage, without a GPU. API access is limited to the providers and models in
  `/task/docs/available_resources.md`.
- The Agent phase allows two hours for implementation and validation. Index
  construction allows 1,200 seconds and at most 8 GiB of index files. Search
  readiness allows 30 seconds; each query response allows 20 seconds, including API calls.
- Read `/task/docs/environment.md` for execution details and
  `/task/docs/available_resources.md` for permitted APIs, models and credential handling.

### Corpus format

`/task/data/catalog.json` is a UTF-8 JSON object with `schema_version`,
`tables` and `joins`. The full catalog is shared across development and
evaluation queries. Dataset inventory counts are recorded in the author README.

Each table provides:

- `table_id` and `group_id`: opaque identifiers;
- `table_name` and `description`: original table name and catalog description;
- `columns`: column objects containing `column_id`, original `name`, `type` and
  `primary_key`; column IDs are scoped to their table;
- `row_count`: the source table's row count; and
- `sample_rows`: at most three rows, using original column names as keys and
  string values. SQL NULL cells are omitted.

Samples are incomplete and chosen independently of the questions: the first
three rows in primary-key order, or frozen SQLite row order when no key is
declared. Text values are truncated to 80 characters and binary values appear as
`<binary>`. A true `primary_key` marks membership in the declared key, not
independent uniqueness of that column. Original table and column names retain
their meaning.

Each public join has exactly `left_table`, `left_column`, `right_table` and
`right_column`, expressed using the supplied IDs. It represents an undirected
column equality: swapping both endpoints preserves its meaning.

### Build interface

The verifier invokes:

```bash
bash /app/submission/build.sh \
  --corpus /task/data/catalog.json \
  --index-dir /work/index
```

The supplied index directory exists and is empty. Honor the supplied path and
put all generated index files inside it. The index may contain only regular
files and directories, totaling at most 8 GiB. Return exit status `0` within
1,200 seconds.

### Search interface

After a successful build, the verifier invokes:

```bash
bash /app/submission/search.sh --index-dir /work/index
```

Keep this process alive across successive queries. Within 30 seconds, emit this
readiness object followed by a newline:

```json
{"ready":true}
```

Then read one JSON query per stdin line. Each query has exactly this shape:

```json
{"query_id":"opaque-query-id","question":"A natural-language business question."}
```

For each query, emit and flush one JSON response per stdout line within 20
seconds of receiving it, including any API calls. A failed warm-up does not reduce a scored query's result: the verifier restarts the service and still sends the real query with its own full deadline. One synthetic, unscored warm-up query precedes the hidden
questions. Write diagnostics to stderr and stop serving at EOF. Each response,
including its newline, must be at most 65,536 bytes.

Queries run sequentially in the frozen hidden query-file order. Query IDs remain
opaque and may change. Echo the received ID without interpreting it.
The verifier runs submission code as an unprivileged user, with a writable index
and temporary directory. Serving can read the index and submission files. The
verifier container is limited to 512 processes/threads; each submission process
is limited to 256 open file descriptors.

### Output contract

Each response contains exactly `query_id`, `table_ids` and `joins`:

```json
{"query_id":"opaque-query-id","table_ids":["tbl_A","tbl_B","tbl_C","tbl_D","tbl_E"],"joins":[{"left_table":"tbl_A","left_column":"c_000","right_table":"tbl_B","right_column":"c_001"}]}
```

The identifiers above illustrate the format; actual outputs must use real
catalog identifiers and relationships. For every valid response:

- `query_id` must match the received query;
- `table_ids` must contain exactly five distinct real table IDs;
- `joins` must contain zero to six distinct public joins, each with exactly the
  four catalog join fields;
- each endpoint must reference a returned table and a real column of that
  table; and
- the response must contain no duplicate JSON keys or extra fields.

Table order, join order and join direction do not affect scoring. Extra legal
candidates within the budgets are permitted. The entire five-table candidate
set need not be connected or belong to one group.

## Available Validation Data

The Agent receives:

- `/task/data/catalog.json`: the full shared catalog;
- `/task/data/validation/queries.jsonl`: development questions, each
  containing `query_id` and `question`;
- `/task/data/validation/labels.jsonl`: reference labels containing `query_id`
  and `acceptable_plans`, each plan containing `table_ids` and `joins`.

Implement local validation checks as needed using these questions, labels and
the scoring rules below. No public scoring implementation is provided.

## Expected Artifacts

The finalized submission must contain working `build.sh` and `search.sh`
entrypoints and all supporting code/resources under `/app/submission`:

```text
/app/submission/
├── build.sh
├── search.sh
└── ...              # supporting implementation files and resources
```

Only this submission directory transfers to the fresh verifier. It is read-only
to the submitted commands. Globally installed package
changes, files elsewhere, running services and a development index do not
transfer. The verifier builds a fresh index using the submitted entrypoint.
The framework also transfers `/logs/agent/trajectory.json` as protected,
verifier-only evidence for the compliance audit.

## Verification

The verifier checks build behavior, the persistent search protocol, response
validity and complete-plan coverage.

A query earns `1` only when the response covers every table and every join of
the same complete acceptable plan; otherwise it earns `0`. Covering the tables
of one plan and the joins of a different plan does not suffice.

```text
coverage = sum(query scores) / number of evaluation queries
reward = coverage if the required compliance audit is healthy and accepts, else 0
```

All hidden queries remain in the denominator, including failed queries. There
is no partial credit, F1 term, table-count weighting or score threshold.

Duplicate tables or joins, unknown IDs or relationships, invalid endpoints,
extra fields, duplicate JSON keys, malformed or missing responses, and responses
arriving after the deadline fail that query. A build failure or index-limit
violation yields zero overall. A query failure yields zero for that query; the
verifier may restart a failed search process for later queries.

Table-only completeness and the warm p95 latency of completed responses are
diagnostics, without additional reward terms.

Run one independent trajectory/source compliance audit after primary evaluation.
A confirmed violation sets the final reward to zero. Missing trajectories,
unavailable or malformed audit results, and trusted verifier failures produce
zero reward with an invalid-measurement status and a nonzero verifier exit;
they are not measured retrieval failures. The grader has a 3,000-second supervisor
window. The audit session has 1,200 seconds inside a 1,500-second wrapper; the
whole verifier retains its 4,800-second limit. Judge credentials are verifier-only
and are never forwarded to build or search processes.

## Hidden Test Overview

Evaluation uses held-out questions on the same full catalog. Query counts,
split policy, structural separation and answer-size distributions are authoring
metadata, summarized in `README.md`; detailed selection records live outside
the task package in the author's `task_development/join-aware-table-retrieval/`
workspace. They are not needed in the agent request. The response budgets and metric above
define the executable contract.

Full databases, source SQL, original database names, and hidden
questions or labels are not Agent inputs. Semantic table and column names remain
visible, while table and group identifiers are opaque.

## Environment and Available Resources

The task provides 16 CPU cores, 32 GiB RAM and 100 GiB storage, with no GPU. The implementation
budget is two hours. No pretrained weights are bundled, and training is not
required. Choose the indexing and search method within these resources.

Embedding and reranking APIs through OpenRouter or Jina may be used during index
construction and queries. Generative LLM calls for query interpretation, candidate
selection or join reasoning are also allowed through OpenRouter, using only the
four exact Qwen model IDs in `/task/docs/available_resources.md`. That document's
provider/model allowlist and whole-task zero-score penalty apply. API calls count
toward the applicable build, readiness or query deadline. Runtime egress is
restricted to `openrouter.ai` and `api.jina.ai`; the coding agent's own model
service is not a submission resource.

Harbor injects `OPENROUTER_API_KEY` and `JINA_API_KEY` into the agent and verifier;
the verifier forwards them to both build and search processes.
`OPENROUTER_API_BASE_URL` is configured as `https://openrouter.ai/api/v1`.
Read credentials from environment variables, not a container `.env` file. Never
hard-code, print, log or save credentials in code, indexes or artifacts.

Read the task-provided runtime and resource documents:

- `/task/docs/environment.md`;
- `/task/docs/available_resources.md`.
