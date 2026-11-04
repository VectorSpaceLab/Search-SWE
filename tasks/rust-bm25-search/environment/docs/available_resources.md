# Available Resources

Network access is disabled. This task needs no retrieval service or API key.

`/task/data/corpus.jsonl.gz` is the pinned Tevatron mirror of MS MARCO Passage v1: 8,841,823 gzip JSONL records with `docid`, `text` and extra `title` metadata. Index only `text`. IDs cover 0 through 8841822 exactly.

`/task/data/warmup.jsonl.gz` contains 54 public DL20 queries with `query_id` and `query`, without judgments. These are disjoint from dev and used for warmup. Both files are read-only; dev queries and qrels are unavailable during development.

The cached generic crates include byteorder, flate2, memmap2, rayon, regex, rust-stemmers, serde, serde_json, unicode-normalization and zstd. Exact versions and transitive dependencies are pinned in `/app/submission/Cargo.toml` and `/app/submission/Cargo.lock`. Existing search/index engines, prebuilt indexes and external data are prohibited. Implement all core indexing and retrieval in Rust.

[Microsoft's MS MARCO dataset terms](https://microsoft.github.io/msmarco/Datasets) apply separately from the code license.
