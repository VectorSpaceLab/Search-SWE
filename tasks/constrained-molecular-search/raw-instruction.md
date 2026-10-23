# Constrained Molecular Search

## Task Description

Search all 12,446,577 combinations of the frozen BRICS 12M library. A request
specifies one target among DRD2, ESR1, F10, MET, PARP1, inclusive bounds on
molecular properties, and k=10000. Return at most k distinct valid combination
IDs, seeking the lowest true docking scores among truly feasible molecules.
Set order is not scored. No online true docking/target-property lookup exists.

## Requirements

- /task/library: 12M reactions.parquet, synthons.parquet, library.json.
- /task/models: encoder.pt, probe.pt, factorizer_brics_csl_12M.pt,
  apex_brics_csl_12M.pt, prepared before development; their storage still counts.
- /task/train: 1M labeled data, original folds and library definitions.
- /task/dev: queries, candidate membership and labels from the original 1M
  validation fold. This pool differs from the 12M target. Original folds and
  cross-library overlap treatment are documented in /task/docs/available_resources.md.
- /task/runtime: public ID conversion, evaluator, isolated adapter and optional
  reproducible baseline.py. No baseline/starter is mandatory.
- Read /task/docs/environment.md, /task/docs/available_resources.md and
  /task/docs/environment.md. /task is read-only.
- Any algorithm, including unchanged author models, is legal; training is optional.
  No required starter/architecture. Full enumeration, exact RDKit properties,
  all-target surrogate predictions and query-independent indexes are permitted.
- Development/test complete constraint configurations do not cross sides,
  including when the target changes. Test requests arrive individually.
  Preload only query-independent work. Condition filtering, expansion and
  query-related reranking must occur after delivery and within query time.
- No query-specific precomputed answer sets, target labels/official property table,
  external data/models/services, hidden-input access or grading manipulation.
  Deterministic property computation from legal structures is allowed.
  No submission API/network resource is supplied.

### Preparation and search interface

Only /app/submission transfers to the separate verifier. Include all code,
dependencies and frozen artifacts there. Use regular files/directories; symlinks
and special files are rejected. Include retriever.py exporting
prepare(library_dir, model_dir, index_dir) and
Searcher(library_dir, model_dir, index_dir). The verifier calls prepare once,
then creates Searcher. Preparation may load frozen parameters, predict, calculate
properties and build indexes; it must not train or tune. Submitted files are
read-only during verification. Write only to the supplied index_dir/scratch,
honoring TMPDIR. Installations elsewhere do not transfer.

### Output and identifier contract

Searcher.search(query) returns a plain Python list of built-in integer IDs.
The adapter invokes it serially in a resident process. Example:
{"query_id":"example","target":"DRD2","constraints":{"mol_wt":[null,450.0],"logp":[null,3.5]},"k":10000}.
Null bounds are unbounded; omitted properties are unconstrained. Allowed properties
are mol_wt, logp, n_hbd, n_hba, n_rotatable_bonds, tpsa in RDKit units.
Bounds are inclusive. Empty output is valid and earns no hits.
Boolean, floating-point and string IDs are invalid.

Target IDs are 0 through 12446576 in the supplied CSLDataset order:
reaction input order, sorted internal synthon IDs at each reaction position,
last position varying fastest. Public library.py converts ordinals to author
names/SMILES. Development IDs use its own library and candidate membership;
they are not 12M target IDs.

## Available Validation Data

Use `/task/train` and `/task/dev` for public learning and checks. Run `PYTHONPATH=/task/runtime
python /task/runtime/evaluate.py --library-dir /task/dev/library --private-dir /task/dev
--output-dir /app/development-report`. Public search uses its 347,677-member candidate pool and
request k=279; final requests use k=10000.

## Expected Artifacts

Submit `/app/submission/retriever.py` exporting `prepare` and `Searcher`, plus all required runtime
files and frozen artifacts. Use regular files/directories only; dependencies installed elsewhere do
not transfer.

## Verification

### Metrics and failure handling

For a main query, choose true feasible molecules from the full 12M labels,
order ascending by target score then ordinal ID, and take the first k IDs.
Only finite target scores and finite values of all constrained properties enter
the reference; missing labels are never filled and all combination IDs remain
legal. There are 32,189 missing property rows and 38,928 nonfinite scores per
target. Every final main query has more than 10000 truly feasible molecules. For a final main query,
Recall@10000 is the returned-set intersection with the
first 10,000 reference IDs divided by 10,000. Average configurations within each
target, then all five targets equally to obtain Q. Public development uses
Recall@279 against its 279-item reference, preserving the selection fraction.
Small/empty feasible sets are diagnostic and excluded from main quality.
True-property violations cannot hit the reference and still consume output slots;
missing slots are not filled.

Reward equals Q, displayed as 100*Q points: 20% reference recovery earns 20
points; full recovery earns 100. No learned baseline subtraction or reference
solution sets the ceiling. The metric endpoints are zero and one. The optional
simple baseline is a reproducible comparison, not a required implementation or
zero-point threshold. Speed has no separate weight.

Duplicate/illegal IDs, excess cardinality, query/command failure, or a response
over two seconds zero that query's recalls and retain it in the denominator.
Preparation/load failure or timeout, total resource violations, prohibited
label access or grading manipulation zero the whole task.
Report Q, target/configuration recalls, true constraint satisfaction,
output counts, preparation/index cost, resource use and p50/p95/maximum latency.
The submission never receives target scores. Follow `/task/docs/environment.md` for the public
self-check. Test queries and labels are unavailable during development.

### Timing and resource protocol

- Development: 21,600 seconds including implementation, optional training,
  tuning, derived assets and development evaluation.
- Both phases: A100 40GB x 1, 16 CPU cores, 32 GiB RAM, 64 GiB total task storage,
  including provided public data/models, submission and derived artifacts.
- Final cumulative preparation/loading: 3,600 seconds; no training/tuning.
- Submission processes must permit the provided storage accounting; preventing
  descriptor inspection invalidates the submission (see environment.md).
- Query concurrency one. Hard 2.0 seconds per complete response, from before
  query serialization/delivery through returned IDs, serialization, receipt,
  parsing/validation and GPU synchronization. Parsing, inference, property
  calculation, filtering, Top-k and reranking all count. No startup/API time
  subtraction or pooling. At most 10000 IDs; internal order is not scored.
- Query-independent tables may stay loaded; future queries are unavailable.

After a failed query the supervisor may reload Searcher without rerunning
prepare, reusing index_dir. Imports, initial prepare/load and all restart loads
share one cumulative preparation budget. Package missing dependencies in the
submission and avoid fixed writable paths. Stop background processes on completion;
the verifier also terminates submission UID processes after failures/completion.

## Hidden Test Overview

The published property threshold grids are mol_wt=[250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0,
600.0]; logp=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]; n_hbd=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5]; n_hba=[2.5,
3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 10.5]; n_rotatable_bonds=[1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5,
10.5]; tpsa=[30.0, 45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 140.0, 160.0]. Main queries constrain one
to four properties with inclusive ordered bounds. The four selectivity ranges are [0.02,0.06],
[0.06,0.18], [0.18,0.45] and [0.45,0.9], with five private configurations per range. Complete
configurations are split across public and private sides and shared across all five targets;
selection is property-only, without docking-score selection. Public configurations use off-grid
bounds in the same selectivity ranges. Diagnostics use mol_wt<=190 and mol_wt<=0 per target and are
excluded from Q. Minimum feasible counts are 8,349 for public and 272,845 for final main
configurations.

There are 20 private main configurations shared across all five targets, plus
small/empty diagnostics. Public development has 20 distinct configurations and uses k=279, rounded
from 10000*347677/12446577, to preserve the target selection fraction. Use request k for candidate
selection and recall; final k=10000.
The frozen threshold grids and property-only selection rules are in
/task/docs/available_resources.md. Official scored molecular forms use canonical isomeric SMILES;
raw fragment joins may have different descriptors. Public training removes
5,387 measured-identity overlaps; original weights remain unchanged and retain
the inherited exposure to 40 training-fold overlaps. See available_resources.md.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
