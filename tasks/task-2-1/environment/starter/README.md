# Prefix-Truncation Cross-Encoder Starter

This is a complete but intentionally weak long-document reranking service. The
first-stage BM25 Top-100 candidates and their scores arrive in each query record.
`build.sh` creates a disk-backed document store and starts a persistent service.
`run.sh` sends queries to that service and writes the requested top-k JSONL
rankings. Equal scores retain the original candidate order.

The key baseline behavior is in `src/server.py`: every candidate document is
paired with the query once and passed to the fixed Cross-Encoder with
`truncation=True` and `max_length=512`. Text beyond the retained prefix is not
scored. Improve that behavior while keeping the scripts' interfaces and the
fixed-model constraints from the task instruction.
The bundled fixed model is `BAAI/bge-reranker-large`.
