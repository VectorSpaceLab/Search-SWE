# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

Inputs come from [ViDoRe V3](https://huggingface.co/collections/vidore/vidore-v3).
The eight original domains, page images, supplied Markdown and graded qrels are
retained. Images are not re-encoded. Source IDs are mapped to package IDs.

The collection has 19,252 pages. Questions have six language variants. Five
original question families are public in all six languages; the remaining
2,414 families are held out. Variants of one original question do not cross
the split. Domain-scoped retrieval and domain-macro nDCG@10 retain the current
task contract. No answer or bounding-box labels are fabricated.

The eight upstream dataset snapshots are:

| Dataset | Revision |
| --- | --- |
| vidore/vidore_v3_hr | 0cdf0979f2c5a0fd3e335e6373b9da48a9fe3bc3 |
| vidore/vidore_v3_finance_en | 7f432c176d82e27546501ad8064a713ac3071809 |
| vidore/vidore_v3_industrial | e26c864724f5dd71a3d7d739272d95637764cee9 |
| vidore/vidore_v3_pharmaceuticals | 3abd4aa8a9445fb5538a78a19ba50bd57bd22b5c |
| vidore/vidore_v3_computer_science | d5cc75883d92e294f0c0fc2662551c9708a06ebc |
| vidore/vidore_v3_energy | caec06d3c73434d635f710f93bcd898331c59f20 |
| vidore/vidore_v3_physics | a0de276f515acc044b72cae8de53a44bb5a8f1f5 |
| vidore/vidore_v3_finance_fr | 1d808daa08032ffecdf62da151a7f7a8fe2bd0c9 |

The current package has 30 public input rows and 14,484 held-out rows.
Multiple versions of one original question stay in the same split; public
input-row counts therefore exceed the five public question families.

## Source terms

The eight pinned ViDoRe V3 dataset cards above declare CC BY 4.0 for generated annotations, qrels and related metadata. Their licensing sections explicitly distinguish original documents and parsed Markdown: those retain their publishers' terms, recorded in each release's documents_metadata license field. Review those per-document terms when mirroring pages; the annotation license is not a blanket license for the document collection. The model cards specify MIT for the ColQwen2.5 adapter and Apache 2.0 for its compatible base. Existing document attributions and the remapping/preparation history remain applicable.

## Runtime asset sources

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| search-swe/Search-SWE | dataset | a0414ded2b84d92e9968c679401574de9a8ed130 | 19,255 |
| vidore/colqwen2.5-base | model | 92908120384b7a2110c5beda3ab29cbdb2c08e49 | 14 |
| vidore/colqwen2.5-v0.2 | model | dcbe8d9cede518bce830488364ba0e40c873645b | 13 |

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.

## Bundled model documentation

`models/vision-backbone/README.md` is adapted for the task environment, retaining model metadata, source attribution, license information and citations. Original source: `vidore/colqwen2.5-base`, revision `92908120384b7a2110c5beda3ab29cbdb2c08e49`, file `README.md`. The task restores the bundled copy using the size and SHA-256 in `assets.json`.
