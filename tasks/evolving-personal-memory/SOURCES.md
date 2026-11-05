# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

Conversation histories and question criteria come from
[Memora](https://github.com/geniesinc/Memora/tree/a6493188efc836d6511ed5e4163fe3ba87da30ff).
The histories are synthetic. All 27,614 sessions for 30 personas and all
600 source questions are retained.

Criteria are deduplicated within a question by exact criterion text, expected
decision and type. No new questions or criteria are generated. The split is
question-level and intentionally shares personas and the complete public history.
Search selects up to 350 eligible original records; the verifier passes their
complete text to a separate answer process. FAMA retains source memory/forgetting
criterion semantics.

The current package has 5 public input rows and 595 held-out rows.

## Source terms

The [pinned Memora repository](https://github.com/geniesinc/Memora/blob/a6493188efc836d6511ed5e4163fe3ba87da30ff/LICENSE) uses Apache 2.0. Retain its copyright, license and applicable notices for the synthetic histories and source criteria. This package changes the public/held-out split and deduplicates criteria as described above; it does not describe the generated conversations as human records. The upstream notice files supplied with the package are retained.

## Runtime asset sources

All remote manifest entries use immutable revisions.

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| search-swe/Search-SWE | dataset | ba49ab6cccbec42042e62e02b66eef30d73ca0c7 | 1 |

4 small metadata/example files are bundled under the local paths in
[assets.json](assets.json); those files need no separate upload.

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.

## Bundled source documentation

`data/corpus/licenses/source-data-README.md` is adapted from the source documentation for the supplied conversation histories, retaining source attribution and license information. The task restores the bundled copy using the size and SHA-256 in `assets.json`.
