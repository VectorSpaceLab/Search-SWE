# Available Resources

Use the supplied molecule libraries, local checkpoints and installed runtime.

## Local resources

- `/task/library`: target molecule library.
- `/task/train`: training inputs.
- `/task/dev`: public development inputs.
- `/task/models`: read-only `encoder.pt`, `probe.pt`, `factorizer_brics_csl_12M.pt` and `apex_brics_csl_12M.pt` checkpoints.
- `/task/runtime`: task helpers and public self-check interfaces.

The supplied checkpoints count toward storage and may be reused or improved. Training and rebuilding caches are optional; changes, predictions and derived assets count within the applicable development and final preparation budgets. Read the task instruction for the interfaces and public self-check.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Data semantics

The target contains 12,446,577 legal combination IDs. The original scored SMILES use RDKit canonical isomeric form. Raw sticky-fragment joins can produce a different tautomer, so their RDKit descriptors can differ from the reference descriptor values. RDKit 2024.3.5 is installed in both phases. Computing deterministic properties yourself from legal structures is allowed.

Missing target SMILES, properties and scores remain missing. All IDs remain legal, but a reference candidate must have a finite target objective and finite values for every constrained property; missing values are never filled. Target docking scores and the reference target-property table are not supplied and have no online lookup interface.

The public training and validation folds exclude rows overlapping the target labels. The supplied encoder has prior training exposure to 40 of those overlapping rows. Public development uses the retained original 1M validation pool, with its own library IDs and `candidate_ids.npy`; final evaluation uses the complete 12M pool. Complete constraint configurations are disjoint across these pools for all five targets.

## Source terms

Inputs come from Numerion Labs' APEX (ICML 2026). Data are licensed under CC BY 4.0; checkpoints and APEX code under CC BY-NC 4.0; and the apex_topk extension under MIT. Retain Numerion Labs' and the paper authors' attribution and the supplied license notices, including the CCCL header notices.

## Network and resource restrictions

Use only the supplied local data/models and installed software. No external retrieval, embedding, docking, reranking, generation or answer API is a task resource. No task API key is injected or required. External downloads, data, models and benchmark answers are prohibited. Do not access hidden grader data or manipulate infrastructure. A prohibited label, resource or integrity action invalidates the whole submission.
