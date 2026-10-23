I need to find papers whose methods could help address a research problem. Given a proposal describing the problem and motivation, return a short ranked list of papers worth consulting for methodological inspiration. Papers on the same topic are useful only when their methods are relevant to the proposed work. Build an executable retrieval system over the supplied collection.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime, available resources and API restrictions. The collection is `/task/data/corpus.jsonl`, labeled examples are at `/task/data/examples.jsonl`, and the local model is `/task/models/stella_en_400M_v5`.

Use only the supplied task material and permitted APIs. Do not obtain external papers, datasets, additional pretrained weights, benchmark answers or hidden relevance judgments. External search services and hard-coded query-to-result mappings are prohibited. Keep credentials out of source code, logs and artifacts.

You have 6 hours for development, with one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and 100 GiB storage.

Create the complete submission under `/app`, including executable `/app/build.sh` and `/app/run.sh`. The separate verifier receives these files but does not inherit installed packages or running processes. `/task` is read-only. During verification the submission runs as a non-root user with `/app` read-only; the corpus, local model and resource documents remain available, while the examples file does not. Keep generated files in the supplied index directory and write results to the requested output path.

The verifier first prepares the engine with:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /app/index
```

Complete indexing and initialization, including any resident service, and return status zero within 1,200 seconds. The index directory starts empty and its path may differ from this example. Hidden queries are provided after initialization succeeds.

The complete query batch is then submitted through:

```bash
/app/run.sh \
  --index-dir /app/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 3
```

Read `query_id` and `text` from each query. Write one UTF-8 JSONL result per query, preserving its ID: `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. Cover every query exactly once, in any query order. Return at most three distinct corpus documents with finite numeric scores, sorted by descending score; ties follow corpus order. An empty result list is valid.

The entire query batch must finish with status zero within **12 seconds**, including API waiting and output writing. A build or query timeout, command failure, invalid output or integrity violation gives score zero.

Retrieval quality is evaluated by mean Recall@3 on hidden queries. Maximize this metric to improve your final score.
