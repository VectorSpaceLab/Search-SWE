# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

PDFs and questions are the MMLongBench-Doc and FinRAGBench-V branches of
[DocLensDatasets](https://huggingface.co/datasets/dwzhu/DocLensDatasets/tree/7a54da77adf09d2c88c67f1bbb725718260f1dc1).
The source evaluation code is
[DocLens](https://github.com/dwzhu-pku/DocLens/tree/1d7e6e6452c71b665b9029e5fef374357d9f3788).

Original PDFs are retained. Identical PDFs are shared across branches, yielding
433 documents and 29,149 pages. Uniformly extracted per-page text supplements
the PDFs. Questions identify the source document.

Four incorrect upstream answer-format fields are corrected deterministically;
questions and canonical answers remain unchanged.
MMLongBench-Doc uses the source answer-extraction prompt and numeric
comparators for integer and float answers. Its text, list and unanswerable
answers go directly to a task-specific binary semantic judge. FinRAGBench-V
retains its source answer judge. The two branches are equally weighted.
Out-of-range source page references are excluded only from citation diagnostics.
Citation diagnostics do not change the primary answer score.

The current package has 5 public input rows and 2,471 held-out rows.

## Source terms

The original [MMLongBench-Doc license section](https://github.com/mayubo2333/MMLongBench-Doc#-license)
specifies CC BY-NC 4.0 for data and Apache-2.0 for code. Its data-specific
attribution and noncommercial terms apply to the corresponding derived inputs
and annotations; the code license must not be substituted for the data license.

The pinned [FinRAGBench-V dataset card](https://huggingface.co/datasets/zhaosuifeng/FinRAGBench-V/blob/d0d65255c94e687caa81ac9da7758ed25ff046a5/README.md)
declares Apache-2.0. Preserve attribution to DocLens, both original datasets and
the PDF publishers. These dataset-level declarations do not independently
establish rights over every third-party PDF. Original PDFs stay at their
verified upstream pins; derived page text retains applicable source-document
terms. Extraction and answer-format corrections are disclosed adaptations.
No single replacement license is asserted for the combined material.

## Runtime asset sources

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| dwzhu/DocLensDatasets | dataset | 7a54da77adf09d2c88c67f1bbb725718260f1dc1 | 433 |
| search-swe/Search-SWE | dataset | 299bcc817c8e795d8be1d20ad1dd39406be1263e | 436 |

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.
