# Task-2-4 ReAct starter

Improve this baseline to maximize Gold Recall@5. It uses a SQLite FTS5/BM25
search service and a small ReAct loop: choose a search, observe candidate
documents, and repeat or finish with five document IDs. All queries share the
index and service; each query has its own planner state and trace.

```bash
/app/build.sh --corpus /task/data/corpus.jsonl --index-dir /app/index
/app/run.sh --index-dir /app/index \
  --queries /task/data/validation/queries.jsonl \
  --output /app/validation-results.jsonl
```

`build.sh` streams the corpus into SQLite, indexing the first 6,000 characters
of each document. It reuses an index with a matching corpus fingerprint and
starts the service again in a fresh verifier. No model download is needed.

With `OPENROUTER_API_KEY`, the planner uses the allowed `REACT_MODEL` (default
`qwen/qwen3.5-9b`) through `OPENROUTER_API_BASE_URL`. Without that key, the
baseline performs one lexical search and returns five results, so the interface
can be exercised offline. These are submission model settings, separate from
the PDF tasks' private answer/trajectory judge settings.

The loop makes at most 20 searches per query, counting the initial search.
`--max-rounds` can lower that limit. A retrieval round is one search action that
returns a ranked candidate set; a batch of independent searches counts each
search separately. LLM planning and selection from already observed documents
do not count as additional searches. The trace next to the result file records
the search actions and their returned IDs. The trace is diagnostic output from
the submission, not a trusted verifier-side counter for arbitrary rewritten code.

The verifier imposes no individual query deadline. Its existing shared execution
and phase budgets still apply. HTTP requests have transport timeouts to report
unresponsive services.

Useful optimization points are document coverage/chunking, retrieval and
reranking, query decomposition, observation selection, stopping rules, and
final document selection. You may modify or replace the starter while preserving
the build/run interfaces, at most 20 retrieval rounds, and exactly five valid
document IDs. The scoring metric remains only Gold Recall@5.

Files:

- `src/build_index.py`: index construction and service startup.
- `src/search_service.py`: concurrent local lexical search.
- `src/run_search.py`: model actions, observations, candidate fusion, and output.
