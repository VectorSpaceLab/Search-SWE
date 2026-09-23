# Task: task-1-x-1

## Task Description

Build an executable, persistent Faiss retrieval backend over the supplied vector corpus and tag metadata. Given a query vector and a set of required tags, return the nearest corpus documents that satisfy every required tag.

The objective is to recover the exact filtered Top-10 under strict latency and resource constraints. You may use any Faiss-based indexing and retrieval architecture that satisfies the executable interface and task requirements.

## Requirements

- Create or modify submission files only under `/app`.
- Treat `/task` as read-only.
- Use only the supplied vectors and metadata as retrieval data. Do not use external retrieval services, external embeddings, downloaded reference answers, hidden evaluator data, or hard-coded query-to-result mappings. Public validation data may be used for development and tuning.
- Retrieval must use a persisted Faiss ANN index over the corpus. Merely creating an unused Faiss index does not satisfy this requirement. Full-corpus brute-force distance computation must not be used as the default query strategy. Exact search over filtered or candidate subsets and exact candidate reranking are allowed.
- Read `/task/docs/environment.md` for the installed runtime, packages, and system tools.
- `build.sh` and `run.sh` must be executable files under `/app`.
- `build.sh` must complete within **600 seconds**.
- A query earns credit only if it completes within **15 milliseconds**.
- The evaluator allows up to 120 minutes for the Agent to complete this task; plan implementation, validation, and debugging within this time budget.

### Build interface

The verifier invokes:

```bash
/app/build.sh \
  --vectors /task/data/corpus/vectors.u8bin \
  --metadata /task/data/corpus/metadata.spmat \
  --index-dir /path/to/index
```

`build.sh` must build and save all index and runtime artifacts required by the retrieval service, then exit with status `0`.

Save a trained Faiss ANN corpus index as `index.faiss`, readable with `faiss.read_index`, covering all supplied vectors (`ntotal=N`), with dimension 192 and the L2 metric. An exact-only `IndexFlat`, including a wrapped one, is not an ANN corpus index. Save metadata indexes, ID mappings, original vectors needed for accurate distances, and all other required state inside `--index-dir`. Saved files must be regular files without symlinks.

Use the supplied paths: the verifier's index directory may differ from this example. The paths supplied to build become unavailable before the first service load, and the saved index is later relocated. Do not depend on those input paths, the original index pathname, a surviving build process, or generated artifacts outside `--index-dir`.

### Search interface

After a successful build, the verifier invokes:

```bash
/app/run.sh --index-dir /path/to/index --serve
```

After loading, write exactly `{"status":"ready"}` as one JSON line to stdout and flush it. Read one JSON request per line from stdin and immediately write and flush one corresponding JSON response. Do not wait for stdin EOF. Diagnostic output belongs on stderr.

Each request contains `query_id` (string), `vector` (192 numeric values), `filter` (an object of the form `{"all":[tag_id,...]}`), and `k` (an integer in `[0, 100]`). Tag IDs are nonnegative integers. All scored queries use `k=10`.

The verifier sends requests strictly one at a time; the next query is unavailable until the current response has been checked. The 15 ms deadline starts when the verifier begins writing the request and ends after it receives and decodes the response JSON. Evaluator-side request serialization and result validation are excluded. Loading is timed separately, so initialize runtime work before emitting `ready`.

### Output contract

Each response line must be a JSON object with the following shape; this example illustrates a request with `k=1`:

```json
{"query_id":"query-id","results":[{"doc_id":1234,"distance":17952.0}]}
```

For every valid query:

- Preserve the input `query_id`.
- Use the original zero-based corpus row number as `doc_id`. A nonzero metadata entry denotes membership in that tag.
- Every returned document must contain **all** required tags, including conjunctions with more than two tags. Repeated tags have no additional effect; an empty tag list matches the whole corpus.
- Unknown or unused tags, or an empty intersection, yield no matches.
- Return exactly `min(k, matching_document_count)` distinct, valid documents. Do not pad with `-1`, duplicate results, or documents outside the filter. For `k=0`, return an empty list.
- Report finite numeric distances using squared Euclidean distance on the original vector values, with absolute error at most `0.001`.
- Sort results by ascending `(distance, doc_id)`. Equivalent matching documents at the exact Top-K distance boundary are accepted, but cannot replace a strictly closer neighbor.
- Produce identical responses for identical requests across process restarts and index relocation.

The distance is:

```text
distance(q, x) = sum((float(q[i]) - float(x[i])) ** 2 for i in range(192))
```

Cast before subtracting uint8 values. Do not normalize vectors or change the metric. Approximate candidate generation and quantization are allowed, but every scored query must recover the exact filtered Top-K and report accurate original-vector distances.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus/vectors.u8bin` — 10,000,000 precomputed vectors, each with 192 uint8 dimensions.
- `/task/data/corpus/metadata.spmat` — document-by-tag CSR metadata with 200,386 possible tags.
- `/task/data/corpus/config.json` — corpus dimensions, data types, and distance metric.
- `/task/data/validation/queries.jsonl` — public development queries using the same schema as hidden queries.
- `/task/data/validation/ground_truth.jsonl` — exact filtered Top-10 references for the public queries.
- `/task/data/example/` — an independent 64-document corpus with 17 queries and exact answers for optional functional development. These examples do not add scored cases.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files under `/app`, together with the implementation and any additional runtime dependencies.

```text
/app/
├── build.sh          # executable index-build entry point
├── run.sh            # executable persistent-query entry point
├── src/              # optional implementation modules
└── README.md         # optional implementation notes and self-test details
```

## Verification

After the Agent phase, the Harbor verifier runs the submission in the same task environment and uses the private test split. The verifier checks the following items:

1. **Index construction and persistence.** The submission must build a valid Faiss ANN corpus index and persist all state required for retrieval under `--index-dir`. The saved index must remain functional when the original build inputs are unavailable, across fresh service processes, and after index-directory relocation.
2. **Execution constraints.** build.sh must complete within 600 seconds and each query within 15 milliseconds end-to-end.
3. **Interface and output correctness.** The verifier checks the executable interfaces, filtering semantics, document IDs, result counts, uniqueness, distance accuracy, ordering, determinism, and output format.
4. **Retrieval correctness.** Scored queries must return the complete exact filtered Top-K within the query latency limit. Partial Top-K recall does not satisfy the correctness requirement. Equivalent ties at the exact Top-K boundary are accepted.

Submissions must not access hidden evaluation data, hard-code evaluation answers, use external answer lookup, bypass the required retrieval process, or manipulate evaluation infrastructure.

## Hidden Test Overview

The hidden evaluation contains held-out queries with private relevance judgments. The hidden queries are disjoint from the public development examples and are not copied into the Agent-visible environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — a concise description of the installed Python environment, system runtime, and commonly available packages and tools.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. The credentials described there are injected by Harbor at runtime and must not be placed in the task package or Docker image.
