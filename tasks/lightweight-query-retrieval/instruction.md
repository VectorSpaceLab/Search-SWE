I need a retrieval service that can process a batch of search queries quickly while maintaining useful search results. Return up to ten documents from the collection specified by each query. The goal is to reduce total retrieval time after meeting the required search quality.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the environment and files. The corpus is `/task/data/corpus.jsonl`, labeled examples are `/task/data/examples.jsonl`, and the supplied model is `/task/models/Llama-3.2-1B`. Network access and external APIs are unavailable. Do not use external datasets, additional pretrained weights, hidden labels, precomputed test answers or hard-coded input-to-answer mappings.

You have six hours for development, with one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and 100 GiB storage. Keep the complete submission under `/app`, including executable `build.sh` and `run.sh`. This directory is transferred to a separate verifier; development processes and installed packages are not transferred. The corpus, supplied model and resource documents remain available, but the examples do not. `/app` and `/task` are read-only during verification. Write generated files to the index directory during build and to `$TMPDIR` during service execution.

The verifier builds the index with:

```bash
/app/build.sh --corpus /task/data/corpus.jsonl --index-dir /path/to/index
```

Complete within 1,200 seconds and exit with status zero. The index directory starts empty and becomes read-only after build. The verifier then launches the service:

```bash
/app/run.sh --index-dir /path/to/index --serve
```

Load the service and write `{"status":"ready"}` as one JSON line to stdout within 120 seconds. Keep the process running. For each subsequent JSON line on stdin, return one JSON line on stdout. Use stderr for logs.

Requests have the form `{"queries":[{"query_id":"request-id","collection":"corpus1","text":"query text","instruction":"retrieval instruction"}],"top_k":10}`. Return `{"results":[{"query_id":"request-id","results":[{"doc_id":"document-id","score":1.0}]}]}`. Cover every query exactly once. Return distinct, valid document IDs from its requested collection, ordered by decreasing finite numeric score. The order of query results is unrestricted.

Complete a warm-up batch drawn from the supplied examples within 60 seconds. The verifier then sends all 1,271 hidden queries in one request. Finish this request within 120 seconds. Timing includes receiving and processing the queries, retrieval, ranking and returning the response; index construction, model loading and warm-up are excluded. Evaluation uses three fresh service instances, each with fresh temporary storage, and scores their median retrieval time.

Search quality is nDCG@10 using the original relevance grades as gains, averaged equally across the three collections. Every timed run must reach **0.45** or higher; otherwise the score is zero. Valid submissions meeting this requirement earn higher scores for lower median retrieval times. A median time of **0.8 seconds** or more earns zero.

The evaluation harness also preserves your execution trajectory. Final credit requires an integrity audit of this trajectory and your submitted files against the resource and data restrictions above. An unavailable or unsuccessful audit earns zero. Normal corpus-derived indexes, preprocessing and parameters trained using the supplied resources are allowed; poor retrieval quality or speed alone is not an integrity violation.
