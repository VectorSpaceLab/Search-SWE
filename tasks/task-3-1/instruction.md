# Task: Task-3-1

## Task Description

Repair and optimize the supplied sparse retrieval system over a large corpus.
Each document and query is represented by a set of opaque term IDs. Given a
query, return the most relevant corpus documents while keeping total search
wall time low.

The submission must satisfy the held-out retrieval-quality requirements and
process the complete hidden query set within 30% of the corrected, unpruned
starter wall time measured by the verifier in the same environment. You may
replace the starter index or retrieval algorithm as long as the executable
interface and output contract are preserved.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Do not use precomputed hidden query-to-document mappings, hidden relevance
  judgments, or external datasets/services containing evaluation answers.
- Build retrieval state from the supplied corpus through `build.sh`; do not
  require undeclared persistent files from the verifier.
- `build.sh` and `run.sh` must be executable files under `/app`.
- Implement all submission logic in Python source code. `build.sh` and `run.sh`
  may be thin Bash wrappers for argument parsing and launching Python, but all
  indexing, retrieval, scoring, pruning, and ranking logic must be Python.
- Do not add or compile native submission source code, including C, C++, Rust,
  or Go, and do not have `build.sh` produce a native executable. Preinstalled
  Python packages such as NumPy may be used through their normal APIs.
- The submission build and search path must be single-process and single-threaded:
  do not use multiprocessing, worker pools, threading, joblib, Ray, or parallel
  query execution. The verifier environment is limited to one CPU, so additional
  threads cannot obtain extra aggregate CPU throughput; CPU limitation does not
  by itself authorize or make parallel execution valid.
- Read `/task/docs/environment.md` for the runtime and resource limits.
- Read `/task/docs/index_format.md` before changing the starter index. The
  documented format is an implementation detail and may be replaced.
- Read `/task/docs/available_resources.md` for the local dependency policy.
- The evaluator allows up to 120 minutes for the Agent phase.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

`build.sh` must create all persistent index and runtime artifacts under the
provided `--index-dir` and return status `0` only when the index is ready.
The build step may use public statistics located next to the corpus, but may
not require additional undeclared paths.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

`run.sh` must process every supplied query exactly once, preserve input query
order, and write one result object per input query. Required runtime state must
come from the supplied index directory and query file.

### Input format

Documents and queries use JSONL. A document has the form:

```json
{"doc_id":"document-id","terms":["term-id", "term-id"]}
```

A query has the form:

```json
{"query_id":"query-id","terms":["term-id", "term-id"]}
```

The terms in each row are unique opaque strings. Their lexical value, numeric
appearance, input order, and position do not encode relevance.

## Output contract

Each output line must be a JSON object with this shape:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

For every valid query:

- `query_id` must identify the corresponding input query;
- results must contain at most 100 items;
- every result `doc_id` must occur in the supplied corpus;
- document IDs must be unique within a query;
- every score must be finite and numeric;
- results must be ordered by descending score; and
- equal-score results must be ordered by opaque document ID in ascending
  lexicographic order.

Returning fewer than 100 results is valid but may reduce Recall@100.

## Available validation data

The following files are available to the Agent:

- `/task/data/corpus.jsonl` — the full corpus;
- `/task/data/validation/queries.jsonl` — validation queries;
- `/task/data/validation/qrels.tsv` — validation relevance judgments;
- `/task/data/validation/stats.json` — validation term and document-frequency
  statistics;
- `/task/data/validation/reference_top100.jsonl` — validation regression rankings.

The formal hidden query split and hidden relevance judgments are verifier-owned.

## Expected artifacts

The finalized submission must contain executable `build.sh` and `run.sh` under
`/app`:

```text
/app/
├── build.sh
├── run.sh
├── src/              # optional Python modules
└── README.md         # optional notes
```

All required persistent search artifacts must be written beneath the
`--index-dir` supplied to `build.sh`.

## Corrected starter baseline

The verifier uses a corrected, unpruned starter as the latency baseline. It:

- retains every corpus term and every posting;
- does not apply DF, prefix, or other posting-list pruning by default;
- uses the set-valued corpus/query input without weights;
- builds a consistent dictionary, metadata, and posting layout; and
- performs unpruned binary/IDF-overlap search.

Any optional pruning flag in starter code is for explicit local experiments
only and is not used for the verifier baseline.

## Verification and reward

The verifier rebuilds the submission from the full corpus and runs it on a
private query split. It checks retrieval integrity, executable behavior, output
validity, retrieval quality, and search wall time.

The hidden results must satisfy:

```text
NDCG@10 >= 0.89
qrels Recall@100 >= 0.99
```

The verifier measures candidate and corrected-starter wall time with external
process wrappers under the same workload and resource allocation. The candidate
must satisfy:

```text
candidate wall time <= 0.30 * verifier-measured starter wall time
```

The reward is binary:

- all three conditions pass: reward `1`;
- any quality, latency, build, run, or output condition fails: reward `0`.

Submission-reported lookup counters or internal timing are diagnostic only and
do not replace verifier wall-time measurement.

The formal build and search run offline. The submission must not require
credentials, remote models, package downloads, or external services.
