# Fixed input provenance and publication status

Reviewed against Search-SWE `ebe2e7a7a5592890a81ba10c557d364ba41e9d16` on 2026-10-14. `assets.json` remains the exact byte-level input contract; no asset bytes, split, hash, source revision or model pin were changed by this compatibility update.

The immediate published data source is [search-swe/Search-SWE at 6713b1eb7474e0768e906a0151c76af92f0cfcdd](https://huggingface.co/datasets/search-swe/Search-SWE/tree/6713b1eb7474e0768e906a0151c76af92f0cfcdd), with provenance in its [SOURCES.md](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/SOURCES.md).

The immediate source records the BrowseComp-Plus corpus and a 20-question public selection stratified by 1–5 gold documents with seed 20260909. The packaged source does not record the original upstream corpus revision. On 2026-10-14 the public Tevatron/browsecomp-plus-corpus revision b27b02bc3e45511b8b82a13e6f90ce761df726f6 exposes seven Parquet shards, not this JSONL. Those files cannot be substituted under the existing JSONL hash or input contract. The public questions/qrels are a selected derivative, not the full upstream evaluation split.

| Local input | Published source filename |
| --- | --- |
| `data/corpus.jsonl` | [tasks/agentic-search/corpus.jsonl](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/tasks/agentic-search/corpus.jsonl) |
| `data/validation/qrels_gold.txt` | [tasks/agentic-search/validation/qrels_gold.txt](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/tasks/agentic-search/validation/qrels_gold.txt) |
| `data/validation/queries.jsonl` | [tasks/agentic-search/validation/queries.jsonl](https://huggingface.co/datasets/search-swe/Search-SWE/blob/6713b1eb7474e0768e906a0151c76af92f0cfcdd/tasks/agentic-search/validation/queries.jsonl) |

## Published asset reuse

Search-SWE `ac7dcc1` permits these three published inputs to retain their original `tasks/agentic-search/...` paths, immutable revisions, sizes and hashes. The package passed `--merge-ready` and full local asset verification on 2026-10-17. The earlier namespace restriction is resolved; no asset bytes or source entries changed.

This package references the input files pinned in `assets.json`. Their source provenance and usage terms apply.

## Usage terms and validation boundaries

The `search-swe/Search-SWE` source documentation states that there is no blanket license for all materials; retain underlying source attribution and applicable terms. Reuse of a published mirror and hash agreement do not establish redistribution rights. No upload was performed. The hidden split is excluded from agent mounts but is visible in the repository.

Local runtime files are checked with the repository downloader `--verify-only`. Remote metadata and small-file download checks are recorded in the author evidence for 2026-10-14; a metadata check of a large file is not a fresh full download. Asset verification does not establish task solvability or replace the configured-model trial.
