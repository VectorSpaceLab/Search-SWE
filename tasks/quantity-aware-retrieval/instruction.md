I need to find clinical-study passages that discuss a requested measurement and satisfy a numerical condition. Please build an executable retrieval system over the supplied collection that returns up to ten relevant passages for each natural-language query, ranked by relevance.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime, available files and APIs, and model/provider/endpoint restrictions. These read-only documents are part of the task requirements. Keep credentials out of source code, logs and output artifacts.

The collection is `/task/data/corpus.jsonl`. Labeled examples are available at `/task/data/examples.jsonl`.

Do not obtain hidden questions or judgments, external datasets, outside documents, additional pretrained weights, or answers from external search services. Precomputed or hard-coded query-to-answer mappings are prohibited.

You have 6 hours for development. The runtime provides one GPU, 16 CPU cores, 32 GiB RAM and 100 GiB storage.

Create the complete submission under `/app`, with executable `/app/build.sh` and `/app/run.sh`, and include all files and dependencies required at runtime. Installed packages or live processes from the development container are not transferred. `/task` is read-only. In the separate verifier, `/app` is also read-only and the submission runs as a non-root user. The corpus, model and resource documents remain available there; `examples.jsonl` does not. Use the supplied `--index-dir` for generated runtime artifacts and write results to the requested output path. Do not require additional fixed writable paths.

The verifier first prepares the engine with:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

This call must complete all initialization and return status 0 within 1,200 seconds. Query invocations begin only after it succeeds. The index directory is initially empty and can differ from the example path above.

Queries are then submitted through:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Read `query_id` and `text` from each input query and write one UTF-8 JSONL result record per query, preserving its `query_id`: `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. Return at most ten distinct corpus documents, sorted by descending finite numeric score; ties follow corpus order. An empty result list is valid.

Each query has a 5-second time limit. A timeout scores zero for that query. Build failures, other execution errors, invalid output or integrity violations result in a task score of zero.

Retrieval quality is evaluated by mean nDCG@10 on a hidden test set. Maximize this metric to improve your final score.
