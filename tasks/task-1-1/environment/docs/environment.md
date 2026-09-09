# Bright biology retrieval runtime

The task image is based on the Search-SWE CPU Python 3.12 image with the Codex/npm agent runtime. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` for task scripts.

The image provides the usual local retrieval and numerical packages, including `numpy`, `scipy`, `scikit-learn`, `pyarrow`, `pandas`, `torch`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `faiss-cpu`, `bm25s`, `rank-bm25`, `hnswlib`, `requests`, `openai`, `fastapi`, and `uvicorn`. It also provides `curl`, `jq`, `git`, `build-essential`, and common process/file utilities.

The corpus is mounted read-only at `/task/data/corpus.jsonl`. It contains one JSON object per line with this schema:

```json
{"id":"document-id","content":"short document text"}
```

The three public development queries and public labels are mounted read-only under `/task/data/validation/`. The verifier's hidden data is not mounted there.

The task is CPU-only (`gpus = 0`). A compact local lexical index is usually fast enough for this 57,359-document corpus. If using an embedding or reranking API, cache only non-secret model outputs and keep the API credential in the process environment; do not write it into an index or log.
