# Budgeted Bi-metric Retrieval

## Task Description

Improve Wikipedia passage ranking for NQ questions over a fixed 250,000-document subset of BEIR NQ.
Return up to 10 ordered task-local document IDs. No candidate lists are provided; search the full
corpus.

## Requirements

- `/task/public/corpus.parquet`: columns `_id`, `title`, `text`, `source_id` (original BEIR ID), with row i corresponding to ID `doc{i}`. `/task/public/cheap.f32`: row-major little-endian float32, shape (250000,384), unit-normalized bge-micro-v2 document vectors. `/task/public/config.json`: dimensions, encoding and fixed asset accounting.

- `/task/public/dev-queries.jsonl`: 500 queries from the official training release, fields `query_id`, `text`, `vector` (384 finite numbers). `/task/public/dev-qrels.tsv`: official relevance labels mapped to the same corpus, with columns `query-id`, `corpus-id`, `score`.

- The fixed subset retains all labelled relevant documents for development and test queries, then fills to 250,000 by uniform sampling without replacement, seed 20261021. IDs are remapped to task-local `doc{i}`; use `_id`, not `source_id`, in protocol results. All original FP32 document/query representations are preserved without re-encoding or quantization.

- All 3452 BEIR test queries, cheap/expensive query vectors and official qrels are verifier-only. Runtime isolation of a public benchmark does not imply that its questions were never public.

- The trusted oracle holds unit-normalized float32 SFR-Embedding-Mistral document/query vectors (4096 dimensions). It returns Euclidean L2 distances (smaller is better), computed from stored vectors, with float64 accumulation. It exposes no vectors, model weights, arbitrary query scoring, or full-corpus expensive ANN.

### Build, query and oracle interfaces

- Initial invocation: `/app/search.sh --data-dir /task/public --index-dir /work/runtime/index --mode build`. Rebuild from the supplied public inputs and permitted learned parameters. On completion of preprocessing, index construction and loading, write exactly `{"op":"ready"}` as one flushed stdout line, then wait for queries. All protocol I/O is JSONL; diagnostics go to stderr. Each protocol line is limited to 1 MiB.

- On a query, stdin receives `{"op":"query","token":"opaque-token","text":"question","vector":[...]}`. The token is an unpredictable current-query handle. No future query is disclosed.

- To obtain distances, emit `{"op":"score","token":"opaque-token","doc_ids":["doc0","doc1"]}`. The response is `{"op":"scores","token":"opaque-token","distances":[0.1,0.2],"used":2,"remaining":18}` in the same document order. Batches must be nonempty. Repeated documents each consume another call. Cache scores within the current query if desired. The first request that exceeds the limit invalidates the query; ignored errors do not restore its validity.

- Emit the final response `{"op":"result","token":"opaque-token","doc_ids":["doc1","doc0"]}`. IDs must be known, unique, exact strings; up to 10 are allowed, including an empty list. Order is the ranking; no numeric result scores are required. Returned documents need not have been expensively scored.

- The worker persists for successful queries and is suspended between them, together with descendants. A failed/expired query kills the worker family. Before another query the verifier may invoke the same command with `--mode load` to restore the existing index and emit ready. Aggregate initial build and subsequent loading time must stay within 3600 seconds; a failed build or reload, or an exhausted startup budget, invalidates the whole submission. Query failures themselves receive zero while retaining every test query in the mean.

## Available Validation Data

- `/task/public/config.json` exposes the frozen aggregate grading references B and U; individual hidden query labels/results remain private.

- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. `/task/baseline/search.py` and `/task/baseline/search.sh` provide the simple vector/direct/hybrid baselines, not an optimized solution.

- The separate development service only accepts public query IDs. `/task/tools/oracle_client.py` provides `call('/begin', {'query_id': ...})` and `call('/score', request)` over `/run/oracle/oracle.sock`. Each begin establishes a fresh timed 20-call development session; there is no such reset interface in final verification.

- Self-check with `python /task/tools/evaluate.py --output /app/dev-results.json --limit 20 --command /app/search.sh --data-dir /task/public --index-dir /app/dev-index --mode build`. The helper is a diagnostic client; final resource and process enforcement is verifier-owned. Full development evaluation uses `--limit 500`.

## Expected Artifacts

- Create executable `/app/search.sh` and all custom source/dependencies not already supplied by the runtime under `/app`. Only `/app` is transferred. Parameters learned from permitted public development data may be included. The verifier runs it as UID 10001 with `/app` read-only, in a fresh `/work/runtime` directory. Only the provided index directory and its parent working directory are writable for indexes, caches and temporary files. Packages installed and background processes started during development do not transfer. Development artifacts left under `/app` also count in final storage and are not used as the prepared final index.

## Verification

### Metrics and failure handling

- Each valid test query uses BEIR nDCG@10 with IDCG from all its official qrels, not its candidates. Over-20 calls, over-2-second duration, execution/protocol failure, duplicate/unknown IDs or more than 10 results give that query nDCG=0. Build/startup failure, memory/storage excess or integrity violations give final score=0.

- Let Q be the mean over all 3452 test queries, including failures. B is the highest fixed resource-valid simple baseline mean (dense 20 + expensive rerank, hybrid 20 + expensive rerank, and direct cheap top-10). U is offline exact expensive-vector full-corpus top-10 quality on those same queries. Baseline implementations/parameters are development-selected, and B/U are frozen before evaluation.

- Displayed score = 100 * clip((Q-B)/(U-B),0,1), with Harbor reward equal to score/100. The full-test mean is computed before normalization. Matching B earns zero; reaching/exceeding U earns 100. U is a reference, not a theoretical relevance upper bound. Fewer calls and faster queries do not independently earn credit. Raw Q/B/U, call counts, latency, startup time, memory and index/storage use are reported.

B=0.8460412084949013 and U=0.9117533972383719.

The coding trajectory is transferred separately and protected before submitted code runs. An independent integrity review checks the trajectory and submitted files for forbidden test-answer mappings, hidden-label use and other stated violations. The numeric score is published only after that review passes; missing, failed or malformed review evidence cannot yield a positive reward and is reported separately from an ordinary low score. Zero expensive-distance or model calls are allowed. General indexes, caches and parameters derived from permitted inputs remain allowed.

### Timing and resource protocol

- Final grading: 16 CPU cores, no GPU, 32 GiB total cgroup memory including scoring service, descendants and page cache; 64 GiB total storage including all public/private fixed inputs, submitted code, indexes, caches, temporary files and diagnostic reserve. Immutable preinstalled system software is excluded from storage. Swap is disabled. The bounded workspace has the remainder after fixed assets and a 512 MiB diagnostic reserve; its exact capacity is prepared from actual asset bytes.
- Every query has 20 document scores and at most 2.0 wall-clock seconds, at concurrency 1. Timing includes query delivery, local retrieval, oracle work, sorting, output and suspending the process family. All query-dependent computation belongs inside this time. Build and loading may use public queries only for warming; the expensive service is unavailable during final build/loading.
- During development, 2 hours are available for implementation and experiments. The main container receives 15 CPU equivalents/31 GiB and its separate oracle 1 CPU/1 GiB; they jointly fit 16 CPU/32 GiB. Final grading uses all 16 CPU/32 GiB in one verifier container. Both stages share the 64 GiB accounting rule.
- No external network, additional model API, external pretrained model weights or GPU. The expensive model weights are never exposed. Use supplied text, cheap vectors and public development data. No hidden-query access, precomputed test-answer mappings, tampering with grader/reward, or bypassing the controlled interface to access private vectors. Learning from allowed public development data is permitted. Local Unix IPC and child processes are permitted within the limits.
- No training or particular indexing algorithm is required. Candidate discovery, adaptive scoring, lexical/dense fusion and final ranking are choices. Cheap top-20 then expensive reranking is a legal baseline.
- Two seconds measures this precomputed-vector service, not real-time execution of the large embedding model.

## Hidden Test Overview

All 3,452 official test questions, expensive query vectors and complete test qrels are
verifier-only. Runtime-hidden evaluation of a public benchmark does not imply that its questions
were never public.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
