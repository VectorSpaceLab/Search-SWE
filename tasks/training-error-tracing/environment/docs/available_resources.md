# Available resources

Use the read-only corpus, models and tools under `/task/data`, `/task/models`
and `/task/tools`. There are no additional permitted models, corpora, retrieval
services or task APIs. Do not obtain the clean original Alpaca corpus for
differencing, the omitted full checkpoint, the error-producing adapter or
hidden errors/labels. Coding-provider transport and the independent verifier
audit do not authorize task-service calls; their credentials are not provided
to submitted programs.

## Corpus and public validation

`/task/data/train.jsonl` contains 52,001 records with `id`, `instruction`,
`input` and `output`. IDs are opaque, case-sensitive strings. Data derives from
Alpaca `dce01c9b08f87459cf36a430d809084718273017`, corresponding to Stanford
`alpaca_data.json` at `761dc5bfbdeeffa89b8bff5d038781a4055f796a`;
one record without retained response loss is excluded. Controlled replacements
change answer entities in one source group per record. Labels identify those
modifications; they do not establish individual-token causality.

`dev-queries.jsonl` and `dev-labels.json` provide 50 actual errors in five
complete groups. The 100 hidden errors form ten other groups. Entity-pair
families, modification sets and prompts are split as described in the task
instruction. Groups sharing an error entity have different relevant records;
an error-entity-only fixed list cannot distinguish them. A retrieval ranker
may be trained using public development labels during development.

## Fixed model and training diagnostics

`/task/models/base` is a diagnostic probe derived from Qwen/Qwen2.5-7B at
`d149729398750b98c0af14eb82c78cfe92750796`: all 28 decoder layers in the supplied
NF4 double-quantized state, complete BF16 input embeddings, tokenizer and
64,439 training-derived original BF16 output rows. Keep canonical model and
tokenizer parameters fixed. Selected inference components, quantization/dtype
changes, CPU offloading and fixed-weight gradients are permitted. The probe's
output head is a subset and cannot provide full-vocabulary CE or unrestricted
generation. The model that produced the errors used this base with an adapter;
that adapter is not a supplied or required solver asset.

Training-only diagnostics are `/task/data/base-nll/base-token-nll.npz` (float16)
and `/task/data/base-alternatives/base-token-alternatives.npz` (int32), each
shaped 52,001×512 with the single key `values`. Load with
`numpy.load(path, allow_pickle=False)["values"]`. Rows follow the training
records; `row-ids.json` and `complete.json` identify the corpus and files.
These are full-base training diagnostics, distinct from probe-head CE, and
contain no development/test error supervision. Supplied preprocessing does
not consume development time; additional features and restored arrays count
toward development time and RAM/storage respectively. All provided data/model
files total less than 5,000,000,000 bytes; this differs from runtime storage.

## Starting implementation and terms

A working submission is installed in `/app/submission`. Its
`retriever_service.py` comes from `/task/tools/streamed_source.py`, with
training-derived source routing and layer-streamed fixed-probe inference.
This implementation is also the immutable paired control used in scoring.
Edit or replace the working copy, or create a copy in an empty directory with
`python /task/tools/build_starter.py --output EMPTY_DIR`.

The Alpaca derivative is CC BY-NC 4.0; the complete notice is
`/task/licenses/ALPACA_DATA_LICENSE`. The included model license is Apache 2.0
and does not replace the data terms. No producer-LoRA pipeline, projected
gradient matrix, additional reference checkpoint or external service is supplied.
