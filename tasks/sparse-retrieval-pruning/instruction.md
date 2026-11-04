I need to run a collection of searches over a large corpus and reduce the time spent waiting for the whole set of results. There is already a sparse retrieval system to start from, and both documents and queries are represented by sets of opaque term IDs. Please optimize that system so it returns relevant corpus documents with lower total search wall time for the complete query workload. You may replace the starter index or retrieval algorithm as long as the executable interface and output contract are preserved.

The faster result still needs to retrieve the relevant documents. The submission must meet the held-out retrieval-quality requirements, after which reward increases linearly with throughput improvement: 4× starter-relative speedup earns 0, 10× earns 0.5, and 16× or more earns 1. The verifier measures both systems in the same environment.

Please read `/task/docs/environment.md` for the installed runtime and resource limits and `/task/docs/available_resources.md` for the local dependency policy. Optional starter implementation notes are in `/baseline-starter/README.md`; you may replace its index format. All of `/task` is read-only, and submission files must only be created or modified under `/app`. The agent phase allows up to 120 minutes. Do not use precomputed hidden query-to-document mappings, hidden relevance judgments, or external datasets or services containing evaluation answers. The formal build and search run offline and must not need credentials, remote models, package downloads or external services.

Implement all submission logic in Python source code. `build.sh` and `run.sh` may be thin Bash wrappers for argument parsing and launching Python, but indexing, retrieval, scoring, pruning and ranking must all be Python. Do not add or compile native submission source, including C, C++, Rust or Go, and do not have `build.sh` generate a native executable. Preinstalled Python packages such as NumPy are available through their normal APIs.

Both the submission build and search path must be single-process and single-threaded. Do not use multiprocessing, worker pools, threading, joblib, Ray or parallel query execution. Thin serial shell launch wrappers remain allowed.

The collection to search is `/task/data/corpus.jsonl`. To check retrieval quality as you reduce search time, public development material includes `/task/data/validation/queries.jsonl` for validation queries, `/task/data/validation/qrels.tsv` for relevance judgments, `/task/data/validation/stats.json` for term and document-frequency statistics, and `/task/data/validation/reference_top100.jsonl` for regression rankings. The formal hidden query split and its relevance judgments belong to the verifier. Document and query files are JSONL: a document looks like `{"doc_id":"document-id","terms":["term-id", "term-id"]}` and a query like `{"query_id":"query-id","terms":["term-id", "term-id"]}`. The repeated placeholder in those examples denotes the shape of the array; actual terms within a row are unique opaque strings. Their lexical value, apparent numeric value, input order and position do not encode relevance.

Provide executable `/app/build.sh` and `/app/run.sh` files in the final submission. Optional Python modules may live in `/app/src` and optional notes in `/app/README.md`. The verifier builds with:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

Build retrieval state from the supplied corpus and create every persistent index and runtime artifact beneath that supplied `--index-dir`. Return status 0 only when the index is ready. The build may use public statistics next to the corpus, but it must not require additional undeclared paths or undeclared persistent files from the verifier.

Once the build succeeds, the search interface is:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

The search run must get all of its required runtime state from the supplied index directory and query file. Process each supplied query exactly once, preserve input query order, and write one result object per query. A JSONL output line looks like `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. `query_id` must identify its corresponding input query. Return at most 100 results, with unique `doc_id` values that occur in the supplied corpus and scores that are finite and numeric. Order results by descending score, resolving equal scores by ascending lexicographic order of the opaque document ID. Fewer than 100 results is valid, though it can reduce Recall@100.

The speed improvement will be measured against the unpruned reference starter used by the verifier as its latency baseline. It retains every corpus term and posting, applies no DF, prefix or other posting-list pruning by default, uses the set-valued corpus and query inputs without weights, builds a consistent dictionary, metadata and posting layout, and performs unpruned binary/IDF-overlap search. Any optional pruning flag in starter code is only for explicit local experiments and is not enabled for the verifier's baseline.

For evaluation, the verifier rebuilds your submission from the full corpus and runs it on a private query split. Every round must achieve mean NDCG@10 of at least 0.89 and mean qrels Recall@100 of at least 0.99.

The corpus contains 1,000,000 documents. Each search invocation processes the same 1,000 hidden queries; the public development set contains 200 queries. Both systems run in fresh processes under the same one-CPU, 32 GiB memory allocation. Speedup compares the starter's complete search wall time with the candidate's. Timing includes process launch, Python imports, index loading, reading all queries, retrieval, output writing and process exit. There is no separate warmup, and the OS file cache is retained between calls.

Submission source and the built index are read-only during search. Each invocation receives fresh output and temporary HOME/TMPDIR directories. Do not write to the index, reuse answers across invocations or rely on files from earlier runs. All persistent state must be built from public inputs.

Your build has 3,600 seconds, and each complete search invocation has 900 seconds. Failure of either quality gate in any round, execution or output validity, or the task's integrity rules gives zero reward. Otherwise reward follows the linear speedup scale above; the displayed score is 100 times reward. Submission-reported lookup counters and timings are diagnostic only.
