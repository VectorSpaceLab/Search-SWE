# Fixed input provenance and publication status

Reviewed against Search-SWE `ebe2e7a7a5592890a81ba10c557d364ba41e9d16`. The 2026-10-15 offline revision adds the local embedding checkpoint below. Existing data, splits and reranker pins retain their verified bytes. `assets.json` is the exact byte-level input contract.

The immediate published data source is [search-swe/Search-SWE at 6713b1eb7474e0768e906a0151c76af92f0cfcdd](https://huggingface.co/datasets/search-swe/Search-SWE/tree/6713b1eb7474e0768e906a0151c76af92f0cfcdd), with provenance in its [SOURCES.md](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/SOURCES.md).

The immediate source records a CoIR/APPS-derived corpus and training examples. Its corpus texts match CoIR-Retrieval/apps revision ad8755dfa53f1de865e165d507fa0523502b5682. That upstream revision provides Parquet corpus, queries and relevance records, not the packaged corpus.jsonl and train.jsonl; matching text alone does not establish identical serialized bytes or the same training selection. The six model files retain their original BAAI/bge-reranker-base immutable source.

| Local input | Published source filename |
| --- | --- |
| `data/corpus.jsonl` | [tasks/code-embedding-finetuning/corpus.jsonl](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/tasks/code-embedding-finetuning/corpus.jsonl) |
| `data/train.jsonl` | [tasks/code-embedding-finetuning/train.jsonl](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/tasks/code-embedding-finetuning/train.jsonl) |

## Local embedding checkpoint

`models/bge-base-en-v1.5/` contains eleven original files from [BAAI/bge-base-en-v1.5 at a5beb1e3e68b9ab74eb54cfd186867f64f240e1a](https://huggingface.co/BAAI/bge-base-en-v1.5/tree/a5beb1e3e68b9ab74eb54cfd186867f64f240e1a): safetensors weights, configuration, tokenizer/vocabulary, Sentence Transformers metadata and the model card. The upstream card declares MIT. Every file was freshly downloaded from that immutable revision on 2026-10-15; sizes and SHA-256 values in `assets.json` were computed from the downloaded bytes and checked against the prior source manifest. The weights also match the upstream LFS digest. Both phases mount this model read-only; it is a fixed retriever, not a submitted artifact.

## Published asset reuse

Search-SWE `ac7dcc1` permits these two published data inputs to retain their original `tasks/code-embedding-finetuning/...` paths, immutable revisions, sizes and hashes. The package passed `--merge-ready` and full local verification of all 19 data/model files on 2026-10-17. The earlier namespace restriction is resolved; no asset bytes or source entries changed.

This package references the input files pinned in `assets.json`. Their source provenance and usage terms apply.

## Usage terms and validation boundaries

The `search-swe/Search-SWE` source documentation states that there is no blanket license for all materials; retain underlying source attribution and applicable terms. Reuse of a published mirror and hash agreement do not establish redistribution rights. No upload was performed. The hidden split is excluded from agent mounts but is visible in the repository.

Local runtime files are checked with the repository downloader `--verify-only`. Remote metadata and small-file download checks are recorded in the author evidence for 2026-10-14; a metadata check of a large file is not a fresh full download. Asset verification does not establish task solvability or replace the configured-model trial.

## Bundled model documentation

`models/bge-base-en-v1.5/README.md` is adapted for the task environment, retaining model metadata, source attribution, license information and citations. Original source: `BAAI/bge-base-en-v1.5`, revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`, file `README.md`. The task restores the bundled copy using the size and SHA-256 in `assets.json`.
