I need to find original passages in the Spring and Autumn Annals and its commentaries so I can check what was recorded for a particular reign, year, month, or time window. Please build an executable retrieval system over the supplied collection that returns up to ten relevant event records for each natural-language question, ranked by relevance. Distinguish records of events in the requested period from later commentary discussing that period.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime, available files and APIs, and model/provider/endpoint restrictions. These read-only documents are part of the task requirements. The collection is `/task/data/corpus.jsonl`; labeled retrieval examples and dated corpus examples are at `/task/data/examples.jsonl` and `/task/data/dated_examples.jsonl`. The local model is `/task/models/Qwen3-Embedding-0.6B`.

API use is restricted to the supplied task material. Do not obtain hidden questions or judgments, external datasets, outside documents, additional pretrained weights, or answers from external search services. Precomputed or hard-coded query-to-answer mappings are prohibited. Keep credentials out of source code, logs and output artifacts.

You have 6 hours for development. The runtime provides one GPU, 16 CPU cores, 32 GiB RAM and 100 GiB storage.

Create the complete submission under `/app`, including executable `/app/build.sh` and `/app/run.sh` and all dependencies required at runtime. Installed packages and live processes from the development container are not transferred. `/task` is read-only. The separate verifier runs the submission as a non-root user with `/app` read-only. The corpus, model and resource documents remain available there; the two examples files do not. Use the supplied index directory for generated files and write results to the requested output path. Do not require additional fixed writable paths.

The verifier first prepares the engine with:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

Complete indexing and all initialization, including any resident service, and return status zero within 1,200 seconds. The index directory starts empty and its path may differ from this example. Hidden queries become available only after initialization succeeds.

The complete query batch is then submitted through:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

Read `query_id` and `text` from each input query. Write one UTF-8 JSONL result per query, preserving its ID: `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. Cover every query exactly once, in any query order. Return at most ten distinct corpus documents with finite numeric scores, sorted by descending score; ties follow corpus order. An empty result list is valid.

Batch processing is allowed. The entire query invocation must finish with status zero within 120 seconds, including input processing, encoding, retrieval, reranking, API waiting and output writing. Build or query timeouts, command failures, missing or invalid output, or integrity violations give score zero.

Retrieval quality is evaluated by mean nDCG@10 on a hidden test set. Maximize this metric to improve your final score.

The integrity review runs independently three times. Its reported value is the arithmetic mean of the three binary decisions. A positive task reward requires all three reviews to accept the submission. A missing, failed or malformed review is an evaluation infrastructure failure.
