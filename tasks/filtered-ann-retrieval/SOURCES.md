# Input provenance and publication

The corpus is the YFCC-10M filtered-search dataset released for the NeurIPS 2023
Big-ANN competition. It contains precomputed vectors and tag metadata, not the
original photographs. The competition's [dataset table](https://big-ann-benchmarks.com/neurips23.html)
and [upstream README](https://github.com/harsha-simhadri/big-ann-benchmarks/blob/main/neurips23/README.md)
list this release under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Credit belongs to the dataset creators and NeurIPS 2023 Big-ANN Filter Track
organizers; upstream references and original filenames are preserved below.

| Local file | Original source | Transformation |
| --- | --- | --- |
| `data/corpus/vectors.u8bin` | `https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/yfcc100M/base.10M.u8bin` | Byte-identical copy under a task-local name |
| `data/corpus/metadata.spmat` | `https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/yfcc100M/base.metadata.10M.spmat` | Byte-identical copy under a task-local name |
| `data/validation/queries.jsonl` | Task-selected vectors and tag predicates derived from YFCC-10M inputs | Ten frozen public cases: five retained and five broad-filter additions; query IDs are task-local |
| `data/validation/ground_truth.jsonl` | Task-author computation from the corpus and public queries | Exact filtered Top-10 with original-vector squared L2 |
| `data/example/*` | Task-authored small synthetic example | 64 documents and 17 functional queries, independent of the scored corpus |

The original query sources are `query.public.100K.u8bin` and
`query.metadata.public.100K.spmat` under the same upstream URL prefix. Query
selection originated in the original task's authoring workspace. Version 0.8.0
retains the original five cases per split and adds five from that workspace's
existing development/holdout candidate pool, using tag diversity before new
latency measurements. All twenty source rows, vectors and predicates are distinct;
each split has four single-tag, four double-tag and two triple-tag queries. Query
vectors are unchanged upstream rows. Exact labels for all cases were independently
recomputed by exhaustive float64 squared L2 over every eligible original vector.
The author-only provenance record retains source rows and selection details.

Version 0.11.0 retains original cases 01–05 in each split. Of 27 additional
queries with ten repeated successful reference responses and ten late saved-Luna
responses per query, it assigns the five smallest reference-runtime medians to
public validation and the twenty largest to hidden evaluation; two middle cases
remain unused. Maximum reference latency and source query ID break ties. These
are adaptive development selections, not an independent generalization estimate.
All additions use unchanged rows from the original 100K query-vector file and
the broad predicate `[23]`, matching 3,386,745 documents. Their exact Top-10 labels
were independently computed over the current complete corpus before selection.
The final public/hidden split contains 10/25 distinct vectors, with no cross-split
vector or query-ID overlap. Public cases have seven single-tag, two two-tag and
one three-tag filters; hidden cases have 22 single-tag, two two-tag and one
three-tag filters. The 25 added cases have pairwise disjoint Top-10 document sets.

Author-side source IDs, rankings, before/after files and validation records are
under `task_development/filtered-ann-retrieval/split-10-public-25-hidden-20261023/`
outside the task package. New IDs follow the existing split-specific format;
the additions are shuffled within each split with seed 20261026.

The original author recorded these full-corpus SHA-256 checksums; the migrated
copies have been checked against them:

- Vectors: `589030afcbcc44a50ff798cec935f0980815a02eb7075b224d4f7c12febe96bf`
- Metadata: `2f9c9a533fde31cb062edfdf5c9410f088bb5d7bf4a721ab98c47e3d2954287d`

`assets.json` records the exact sizes and SHA-256 values for eight runtime inputs. The six unchanged corpus/example files retain their official published pins. The updated public files are published at `234406eb7e304478e48905829fc0d3233f5a9f1f` under `tasks/filtered-ann-retrieval/v0.11.0/data/validation/`. All earlier assets and manifest entries are preserved.

Upstream CC BY 4.0 terms and attribution apply to the original dataset and its
derived inputs. The synthetic example files are published
with the task author's authorization; no additional standalone license for
those original files was supplied. Their downstream license should be settled
with the author before official redistribution. The development dataset card
therefore points to these per-file terms instead of claiming one license for
every file. This document does not change the repository's code license.

Verifier-only queries and labels remain in `tests/data/` and are excluded from
the public input dataset and the agent image/mounts. Files under `tests/data/`
will still be visible to readers if this task code is published on GitHub;
runtime isolation is not a promise of private repository storage. Reference
solutions, private credentials and job outputs are excluded from publication.
