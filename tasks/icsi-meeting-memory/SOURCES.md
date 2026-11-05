# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

The history derives from the [ICSI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/icsi/download/),
described by Janin et al., ICASSP 2003. ICSI stands for International Computer
Science Institute. The prepared history covers 67 meetings from the Bmr, Bro
and Bed series, with 53,600 utterances and 719,788 whitespace-delimited words.
Human word-level transcripts are converted into cleaned chronological records;
empty structural annotations are not dialogue.

The 148 question-answer/evidence examples are authored for this task and linked
to transcript excerpts. They are not original ICSI labels and do not have
independent human certification. Five are public and 143 are held out over the
same history. Evidence-grounded answer accuracy requires both a faithful
retrieved fact and a correct answer. The original [ICSI notice](ICSI_LICENSE.html)
is retained. The memory budget counts readable submitted JSON bytes.

The current package has 5 public input rows and 143 held-out rows.

## Source terms

The retained [ICSI license notice](ICSI_LICENSE.html) explicitly releases the corpus and annotations under CC BY 4.0. Preserve ICSI attribution and identify the transcript cleaning as a modification. The 148 task-authored questions and evidence references are additions by the task author, not original ICSI annotations. Their evidence linkage and lack of independent human certification are disclosed above.

## Runtime asset sources

All remote manifest entries use immutable revisions.

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| search-swe/Search-SWE | dataset | d931a7d5645d84f54ee33258b63f7eaae528479f | 1 |
| search-swe/Search-SWE | dataset | 102f2baf7980f81220d8c5519ff97b3edd369e21 | 3 |

The three public validation files are hosted alongside the history and restored
directly to `data/validation/` through [assets.json](assets.json). They preserve
the original five examples byte for byte; the public answer filename is
`ground_truth.jsonl`. The 143 hidden examples remain separate in `tests/data/`.

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.
