# Available Resources

Use the supplied code corpus, training records, local models and installed runtime.

## Local resources

- `/task/data/corpus.jsonl`: code corpus.
- `/task/data/train.jsonl`: training records; you may hold out part of these records for local evaluation.
- `/task/models/bge-reranker-base`: read-only starting reranker checkpoint to fine-tune.
- `/task/models/bge-base-en-v1.5`: read-only, frozen `BAAI/bge-base-en-v1.5` encoder for local inference.
- `/app/starter/train.sh`, `/app/starter/train.py` and `/app/starter/README.md`: editable training starter and usage instructions.

You may use the frozen encoder to mine training candidates or evaluate a split held out from the supplied training data. Keep the encoder fixed.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Fixed retrieval policy

The task instruction defines the fixed embedding branch, BM25 tokenization, Top-200 candidate lists, complete RRF union, neural inference and tie-breaking rules. The same policy applies to the original and submitted checkpoints. It may be used for training-candidate mining and local evaluation; the verifier's retrieval configuration is fixed.

## BM25 scoring

Each distinct query token contributes once, in sorted token order for deterministic summation. With `N` corpus documents, document frequency `df(t)`, token count `dl`, and mean token count `avgdl` over all corpus documents, score each document by:

`sum_t log(1 + (N-df(t)+0.5)/(df(t)+0.5)) * tf(t,d)*2.2 / (tf(t,d) + 1.2*(0.25 + 0.75*dl/avgdl))`

Only query tokens present in the document contribute. An all-empty-token corpus yields zero scores. Take exactly 200 IDs, even when that requires zero-score documents. BM25 mining uses the supplied corpus without model inference.

## Network and resource restrictions

Both task phases run without network access or task API keys. Use only the supplied models and data; external APIs, models, relevance datasets and retrieval/reranking services are prohibited.
