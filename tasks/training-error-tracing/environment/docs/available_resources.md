# Available Resources

Use only the supplied data, models, tools and installed software. No external dataset, model, retrieval service or task API is permitted. Do not obtain the clean original Alpaca corpus for differencing, the omitted full checkpoint, the error-producing adapter, hidden errors/labels or precomputed answers. The coding agent's provider connection is not available to task programs.

## Data and diagnostics

`/task/data/train.jsonl` contains records with `id`, `instruction`, `input` and `output`; IDs are opaque and case-sensitive. `/task/data/dev-queries.jsonl` and `/task/data/dev-labels.json` provide public errors and modified-record labels. These labels describe controlled answer-entity replacements, not individual-token causality. Public labels may be used to train a retrieval ranker during development.

`/task/data/base-nll/base-token-nll.npz` contains float16 full-base token losses; `/task/data/base-alternatives/base-token-alternatives.npz` contains int32 alternative token IDs. Each archive has one `values` array shaped 52,001×512 in training-record order. Load it with `numpy.load(path, allow_pickle=False)['values']`; `row-ids.json` identifies the rows. These training-only diagnostics contain no development/test error supervision and are distinct from compact-probe head scores. Supplied preprocessing does not consume development time; additional features and restored arrays count toward the applicable time, RAM and storage budgets.

## Model and starting implementation

`/task/models/base` contains the fixed diagnostic probe derived from Qwen/Qwen2.5-7B. Its API is documented in `environment.md`. The probe and tokenizer remain fixed; selected inference components, dtype/quantization changes, CPU offloading and fixed-weight gradients are allowed. A separate retrieval ranker may be fitted during development only.

A working submission is installed under `/app/submission`; its source is `/task/starter/retriever_service.py`. This implementation is also the immutable control used in efficiency scoring. The working copy may be edited or replaced. No producer adapter, full checkpoint or precomputed projected-gradient matrix is supplied.
