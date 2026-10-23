# Available resources

Use only the supplied local data/models and installed software. No external
retrieval, embedding, docking, reranking, generation or answer API is a task
resource. No task API key is injected or required. External downloads/data/models
and obtaining benchmark answers are prohibited. The coding agent's own
provider transport is separate and does not authorize submission API calls.

Four checkpoints are provided read-only:
encoder.pt (679304 bytes), probe.pt (10170 bytes),
factorizer_brics_csl_12M.pt (2841529 bytes), apex_brics_csl_12M.pt (157784636 bytes).
They are under /task/models, fixed before development begins, and count toward
storage. They may be reused or improved; training and rebuilding caches are
optional. Subsequent changes, predictions and derived assets count within
development and final preparation budgets as applicable.

The original 1M labeled library and folds support learning and public
validation. The 12M target provides only reactions, synthons, ID mapping and
model assets. Its true docking scores and official property table are absent
from development and have no online lookup interface. Computing deterministic
properties yourself from legal structures is allowed. Source terms are data
CC BY 4.0, checkpoints and APEX code CC BY-NC 4.0, extension MIT, with CCCL's
retained header/license notices; the original license notices are retained with the installed code.

Read environment.md and the task instruction for the interface and public self-check. Do not access hidden grader data or manipulate infrastructure. A
prohibited label/resource/integrity action invalidates the whole submission.


## Sources and data semantics

Inputs come from Numerion Labs' APEX (ICML 2026,
https://proceedings.mlr.press/v306/pedawi26a.html).
The dataset is Zenodo DOI 10.5281/zenodo.17455955 (CC BY 4.0); credit
Numerion Labs and the paper's authors. The full upstream archive is not a
permitted solver input because it contains target answers. Checkpoints are
from DOI 10.5281/zenodo.17456522 (CC BY-NC 4.0).
Bundled APEX code is revision `80e544eff6bbc2b09022a4f780fc9665256a884e`
(CC BY-NC 4.0); apex_topk is `c561eaa264d7def6172fde3fe356808d9a4a3f85`
(MIT). CCCL notices remain with its bundled headers.

The full target contains 12,446,577 legal combination IDs. The original scored
SMILES are already RDKit canonical isomeric SMILES; among 12,414,388 non-null
structures there are no duplicate aliases. Raw sticky-fragment joins can use a
different tautomer from the scored form, so raw RDKit descriptors need not equal
the official descriptors. This is a property/modeling issue to account for,
not an alternative ID mapping. RDKit 2024.3.5 is installed in both phases.

There are 32,189 missing target SMILES/property rows and 38,928 non-finite scores
per target. All IDs remain legal. A reference candidate needs a finite target
objective and finite values of every constrained property; missing values are
never filled. No target score or official target-property table is supplied.

The 1M original table has 1,739,655 rows and folds 0/1 of 1,386,631/353,024.
Official scored canonical identities overlap the target in 5,387 rows; exact
scored-SMILES joins and all five equal score labels confirm these matches.
These labels are removed from both public folds, retaining 1,734,268 rows with folds
1,386,591/347,677. The full target library and original fold membership of retained
rows are unchanged. Forty removed rows had belonged to training fold 0: the
original encoder's inherited training exposure cannot be reversed without
retraining and is disclosed. 

Public development uses only the retained original 1M validation pool, with its
own library IDs and candidate_ids.npy. Final evaluation uses the complete 12M
pool. Complete constraint configurations are disjoint across these sides for
all five targets. The task instruction describes the workload.
