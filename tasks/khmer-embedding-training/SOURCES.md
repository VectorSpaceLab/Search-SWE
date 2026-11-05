# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

The unchanged English corpus is
[BEIR/NQ](https://huggingface.co/datasets/BeIR/nq/tree/b7253e6c379163d024ddb1d6948152a91a2e3b46),
file corpus/corpus-00000-of-00001.parquet, with 2,681,468 rows.
No BEIR training questions or qrels are supplied.

Khmer questions and aliases use the filtered MKQA release in
[Shitao/bge-m3-data](https://huggingface.co/datasets/Shitao/bge-m3-data/tree/a69db8b86e9c1767d193ee0de95e5c4001a71eae),
MKQA_test-data.zip, km.jsonl. All question strings are checked against
[Apple MKQA](https://github.com/apple/ml-mkqa/tree/f964fe1bac4d580cee3d4928572df1f676f8e656).
Malformed character-level aliases and empty aliases in 22 source date records
are removed while preserving canonical date text and valid full aliases.
Questions and canonical answers are not generated or replaced.

The 6,619 filtered IDs are sorted as strings and shuffled with Python
Random(20261014): three public examples, 1,000 held out and 5,616 unused.
The answer-token hit rule follows FlagEmbedding's MKQA evaluator. Both original
and submitted search systems use the same collection and answer matching.
Qwen3.5-9B is development-only; the embedding architecture and tokenizer remain fixed.

The current package has 3 public input rows and 1,000 held-out rows.

## Source terms

The [pinned BEIR/NQ release](https://huggingface.co/datasets/BeIR/nq/tree/b7253e6c379163d024ddb1d6948152a91a2e3b46) declares CC BY-SA 4.0. Preserve its attribution and share-alike terms for the collection. [Apple MKQA](https://github.com/apple/ml-mkqa/blob/f964fe1bac4d580cee3d4928572df1f676f8e656/LICENSE) uses Apache 2.0; the filtered question release is traced back to those original records. The alias cleanup above is a disclosed modification. Multilingual E5-large is MIT; Qwen3.5-9B is Apache 2.0, at the model revisions listed below.

## Runtime asset sources

All remote manifest entries use immutable revisions.

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| BeIR/nq | dataset | b7253e6c379163d024ddb1d6948152a91a2e3b46 | 2 |
| Qwen/Qwen3.5-9B | model | c202236235762e1c871ad0ccb60c8ee5ba337b9a | 15 |
| intfloat/multilingual-e5-large | model | 3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3 | 10 |
| search-swe/Search-SWE | dataset | 8431ce24f7706eb51ff68aef7494f2b2780319a1 | 2 |

The three public examples are stored as `data/validation/queries.jsonl` (`id`, `question`) and `data/validation/answers.jsonl` (`id`, `answers`). Their fixed official copies are under `tasks/khmer-embedding-training/data/validation/` at the revision above, published in [HF PR #11](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/11). Splitting the original combined rows preserves their order, IDs, questions and answer aliases exactly. Recombining the two files reproduces the original records from `asset-metadata/examples.jsonl` (original file SHA-256 `946c2ba70c4d7d12181af62eb04bc5ec0830d5370f9acd34992bdf8558d63a24`). The obsolete bundled copy has been removed; the asset downloader restores the two public files from HF. No held-out data was uploaded.

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.
