I need to find useful information in long documents, and each query already comes with a BM25 Top-100 candidate set. The next step is to decide which of those documents should be read first. Please improve the supplied reranking pipeline so that the five returned candidates are as relevant to the question as possible. Use the supplied local `BAAI/bge-reranker-large` model to rerank the fixed candidates, maximizing retrieval quality on held-out queries within the required interfaces and resource limits.

The part to improve is how the existing candidates are reranked; the candidate set and learned scorer are fixed. Use exactly the candidates supplied with each query: do not add, remove, replace or independently retrieve candidates. You may optimize the surrounding reranking pipeline, but only the supplied local model may perform learned relevance scoring. Do not replace, fine-tune, retrain, distill, quantize or otherwise modify the model, tokenizer or configuration. The supplied model is mounted at `/task/models/bge-reranker-large`. Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the installed Python environment, system runtime, packages and tools, local resources and network restrictions before implementing.

The full documents are available in `/task/data/corpus.jsonl`. To see how changes affect the ranking, use the public development queries at `/task/data/validation/queries.jsonl` and their normalized labels at `/task/data/validation/ground_truth.jsonl`. The public query records use the same schema as hidden queries. Do not use precomputed query-to-document mappings, hidden relevance information, hard-coded mappings, precomputed answer files, external datasets containing evaluation labels or judgments, or external retrieval or reranking services to get relevance judgments or results. Implement genuine reranking over the supplied candidates. The held-out questions have private relevance judgments, are disjoint from the public examples and are not copied into your environment.

Create or modify submission files only under `/app`. Treat `/task`, `/tests` and the task-provided documents as read-only. The total agent allowance for implementation, validation and debugging is 120 minutes. The final package needs executable `/app/build.sh` and `/app/run.sh` files; optional implementation modules can go in `/app/src` and optional notes and self-test details in `/app/README.md`. During verification you run as a non-root user and `/app` is read-only. Store all persistent and runtime-generated artifacts, including preprocessing and cache state, in the supplied `--index-dir`, except for the result file at the supplied `--output` path. Do not require any additional fixed paths.

The verifier starts with:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

It must prepare all required corpus, model and runtime artifacts, start the reranking service, and return exit status 0 only when the system can process queries, within 1800 seconds. It must keep that service available across repeated `run.sh` calls. After `build.sh` succeeds, queries arrive through:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

Rerank only the supplied BM25 Top-100 candidates and write one result object per query, in input query order. `run.sh` must support repeated calls, complete each full query batch within 3600 seconds, and produce valid output on every call.

Write JSONL output with a line shaped like `{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`. That example shows the fields of a result item; `--top-k 5` requires exactly five items for each valid query. Keep the corresponding input identifier in `query_id` so the reranked documents can be matched back to their question. Each `doc_id` must identify one of that query's supplied candidates and each score must be finite and numeric. Document IDs must not repeat within a query. Sort by descending score and, for equal scores, preserve original candidate order as the tie-break.

A valid submission that passes the compliance review is scored by Accuracy@5: a query earns 1 if at least one relevant corpus document is among its first five results and 0 otherwise, and the final score is 100 times the average of those values. Invalid output, a failed build or query invocation, or a rejected compliance review gives zero credit.
