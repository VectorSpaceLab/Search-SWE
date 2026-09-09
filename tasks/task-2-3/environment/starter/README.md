# Task-2-3 starter

This starter is a teacher-side reference baseline. It encodes validation queries with the local Qwen3-Embedding-4B model, receives the frozen 2560-dimensional document vectors through `--doc-vectors`, and searches them with an in-memory FAISS inner-product index. The decoder-only embedder uses its supported `last_token` pooling method, BF16 inference, and the configured retrieval instruction format.

The starter can also evaluate the public labels and report Accuracy@1 and elapsed time:

```bash
/app/starter/run.sh \
  --doc-vectors /task/data/doc.npy \
  --queries /task/data/validation/queries.jsonl \
  --ground-truth /task/data/validation/ground_truth.jsonl \
  --output /app/validation-results.jsonl \
  --report /app/validation-report.json \
  --top-k 1
```

The JSONL output contains the ranked results for every query. The report contains `accuracy_at_1`, hit/query counts, elapsed seconds, and throughput. No build step or persistent index is required.
The fixed `/task/data/doc.npy` file is never modified.
