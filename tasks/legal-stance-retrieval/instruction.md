Please build an executable search system over the supplied court cases. Each query requests `supported`, `refuted`, or `all`: retrieve cases that support the claim, contradict it, or do either, respectively. `all` does not require both kinds to exist.

The corpus is `/task/data/corpus.jsonl`, and examples are provided under `/task/data/examples`. A model is provided at `/task/models/Qwen3-Embedding-0.6B`. Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime and resource restrictions.

You have 6 hours to complete the task. Save all submission artifacts under `/app`; `/task` is read-only. The verifier transfers `/app` to a separate environment with the supplied corpus and model. During verification, your code runs as a non-root user with `/app` read-only; use the supplied index directory for runtime artifacts and the requested output path for results.

Provide executable `/app/build.sh` and `/app/run.sh`. The build command is:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

The build must return exit status 0 within 3,600 seconds. Any required background service must be started by this build.

After the build, the verifier invokes:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 10
```

The entire query batch must finish within **20 seconds**, returning exit status 0. The verifier measures the same batch in five rounds, rebuilding into a fresh index directory and restarting services before each round. It scores the rankings from the median-time batch, placing failed, late or invalid batches after successful ones.

Write one JSONL object per input query, preserving its `query_id`, with the shape `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. Return exactly ten distinct corpus document IDs per query, ranked by non-increasing finite numeric score. Equal-score items may appear in either order; the array order determines the ranking.

Retrieval quality is evaluated by **mean NDCG@10** on held-out queries. A failed build, fewer than three successful query batches, or a failed integrity audit receives zero credit.
