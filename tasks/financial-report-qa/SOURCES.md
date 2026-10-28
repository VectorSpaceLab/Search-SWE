# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

Report text and questions originate from [DocFinQA](https://huggingface.co/datasets/kensho/DocFinQA)
(original revision: 64ebaff62f692495bcc182f45cf9a9606251b19b;
Parquet conversion: 7ab8d931022705be37535159d637de7e4b341fb6).
Human supporting facts originate from [FinQA](https://github.com/czyssrs/FinQA/tree/0f16e2867befa6840783e58be38c9efb9229d742).

The task preserves all 885 complete reports. Evidence facts are aligned to
original Unicode positions using support text and table/header context;
ambiguous or incomplete alignments are excluded. Final answer values are not
used to guess evidence locations. The retained set has 4,241 questions and
6,610 evidence units. Company/year context and 85 subject clarifications come
from filing covers and source headings. The evaluated output is evidence spans,
not numeric answers; earlier answer-generation prototypes do not describe this version.

The current package has 5 public input rows and 4,236 held-out rows.

On 2026-10-28, a review added 18 alternative passage locations across nine
reports, contributing 26 label locations to 18 held-out questions. Each passage
repeats a complete reference table row; its reporting entity, financial item,
period, unit and column meaning were checked against the original location.
The initial alignment had missed these occurrences when date headers were
formatted differently, a column used an equivalent heading, or a table was
split across text blocks. Existing evidence units and locations are preserved.

## Source terms

The [DocFinQA source card](https://huggingface.co/datasets/kensho/DocFinQA/blob/64ebaff62f692495bcc182f45cf9a9606251b19b/README.md) declares MIT, and [FinQA's pinned repository license](https://github.com/czyssrs/FinQA/blob/0f16e2867befa6840783e58be38c9efb9229d742/LICENSE) is MIT. Retain their attribution and the filing identities in the report collection. The dataset notices do not replace any applicable rights in the underlying annual reports. Evidence alignment and the exclusions described above are task adaptations.

## Runtime asset sources

All remote manifest entries use immutable revisions.

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| search-swe/Search-SWE | dataset | 39235bf2ee2378473af70d245b6d8d329e7920a6 | 1 |

2 small metadata/example files are bundled under the local paths in
[assets.json](assets.json); those files need no separate upload.

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.
