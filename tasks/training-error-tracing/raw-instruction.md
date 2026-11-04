# Training Error Tracing

## Task Description

Improve the supplied online training-data retriever so it uses less query time and GPU memory while investigating erroneous language-model answers. For each actual generated answer and its marked erroneous tokens, return up to ten IDs from the fixed training corpus that recover the records affected by the corresponding controlled answer-entity replacement. Keep group-macro Precision@10 at least 0.98 and every group at least 0.80, then reduce the combined query-latency and GPU-memory cost. These modification labels do not establish that each returned record causally caused an individual token. Text retrieval, fixed-model features or gradients, a retrieval ranker and mixed methods are all allowed.

## Requirements

You have 14,400 seconds for implementation, feature/cache computation, retrieval-ranker training, tuning and development evaluation, using one GPU, 16 CPU cores and 16 GiB RAM. You may train a separate retrieval ranker on public development labels during this stage. Do not update the fixed probe or tokenizer, obtain the clean original Alpaca corpus for differencing, obtain hidden queries before delivery, or use hidden labels, verifier files, author-only reference artifacts or prior test answers. Do not obtain the omitted full BF16 base or producer checkpoint, or download, replace or call an additional model, corpus or external task-model API. The coding agent's own authorized provider calls are allowed; your retrieval program must run without external services.

### Query input

Each request is a JSON object with `id`, `instruction`, `input`, `generated_answer`, `input_ids`, `prompt_token_count`, `target_token_indices` and `target_text`. The supplied IDs are the actual prompt-plus-generation tokens, at most 512 tokens. Target positions are nonempty, unique, zero-based positions in that sequence; the causal prediction for position j is at logits j-1. For model computations, use the supplied IDs and preserve all target positions instead of introducing an inexact re-tokenization or truncation. The query has no separate contamination-group label, source-entity label or relevant-ID list. Hidden requests arrive individually after final preparation. All delivered marked target-token IDs are covered by the supplied diagnostic output rows; input IDs continue to use the complete original tokenizer vocabulary.

### Preparation and query commands

Prepare all runtime code and necessary frozen artifacts under `/app/submission/`. Only that directory is transferred to a fresh verifier. Public fixed inputs and tools are mounted separately, read-only. Files elsewhere in the development container, existing services and GPU state are not transferred. Include executable `prepare.sh` and `run.sh`. The verifier calls `prepare.sh --data-dir /task/data --model-dir /task/models --index-dir INDEX` once, then `run.sh --index-dir INDEX --query QUERY_JSON --output OUTPUT_JSON --top-k 10` for each request. Both execute with the submission directory as their working directory, as an unprivileged user. Submission files remain read-only; put mutable working state under the fresh writable `INDEX` directory.

### Output contract

For each query, `run.sh` must exit successfully and write a regular UTF-8 JSON file of at most 65,536 bytes to `OUTPUT_JSON`, containing `query_id` exactly equal to the current query ID and `ids` containing zero to ten ranked, unique IDs from `train.jsonl`. Output symlinks are rejected. A shorter list is valid, with missing positions counted as misses. A malformed, missing or late output, nonzero exit, incorrect query ID, duplicate/unknown IDs or more than ten IDs makes that query's P@10 and P@5 zero and keeps it in the averaging denominator. Preparation failure or timeout, total-resource violations, invalid submission metadata, fixed-probe updates or forbidden private inputs invalidate the whole submission. Infrastructure failures are reported separately.

## Available Validation Data

The read-only training corpus is `/task/data/train.jsonl`, with 52,001 records containing `id`, `instruction`, `input` and `output`. Treat IDs as opaque, case-sensitive strings. `/task/models/base/` supplies a compact diagnostic probe derived from Qwen/Qwen2.5-7B, with a serialized NF4 decoder, complete input embeddings and a subset of the original BF16 output rows. Load it through `/task/runtime/compact_probe.py::load_probe`. Output rows retain original token IDs and cover every delivered marked target token; this diagnostic head does not provide full-vocabulary cross-entropy or unrestricted generation. Keep the supplied probe and tokenizer parameters fixed. Selected inference components, quantization/dtype changes, CPU offloading and fixed-weight gradients are allowed. A separate retrieval ranker may be trained during development. Data/model paths and formats are in `/task/docs/available_resources.md`; the probe API is in `/task/docs/environment.md`.

Training-only fixed-base response-token losses and alternative token IDs are supplied under `/task/data/base-nll/` and `/task/data/base-alternatives/`. These are full-base diagnostics, distinct from the compact probe's output-head scores, with no development/test error supervision. Supplied preprocessing is excluded from development time; supplied bytes and restored arrays count toward storage and RAM respectively. Additional feature computation, probe-gradient features and ranker fitting use your development budget. A working submission is installed under `/app/submission/`. Its source is `/task/starter/retriever_service.py`, which is also the immutable paired control used for efficiency scoring. You may edit or replace the working copy, or copy the read-only `/task/starter/` directory to a new working directory. Public quality checks are available through `/opt/conda/bin/python /task/runtime/score_dev.py --predictions FILE`; their timing fields are self-reported, not final efficiency measurements.

Use `/task/data/dev-queries.jsonl` and `/task/data/dev-labels.json` for development. They provide erroneous generations and the corresponding modified training-record IDs. Development and final evaluation use disjoint entity pairs, modification sets and prompts, with the same fixed corpus and error-producing model. The same erroneous entity may correspond to different relevant training records; use the current request to distinguish them.

## Expected Artifacts

Also include `submission.json` with integer `schema_version` equal to 1, a nonempty `method` string, a `configuration` object and a `frozen_artifacts` array. List trained rankers, precomputed caches/lists and other frozen data artifacts. Each entry needs a `path` relative to the submission directory, its actual `sha256`, and a nonempty `generation` string specifying how it was generated and from which permitted inputs. Paths must stay inside the transferred directory. An empty artifact array is valid if no such artifacts are used. Record enough configuration to reproduce your method from public inputs.

## Verification

### Metrics and score

AP@10 here means average proportion: returned Top-10 IDs belonging to the query group's modified-record set divided by ten. It is Precision@10, not Average Precision. Average within each group and then give all groups equal weight to obtain Q; P@5 uses the first five results and denominator five. Every repetition must reach Q >= 0.98 and every group P@10 >= 0.80; otherwise the score is zero. Failed or missing requests remain in these denominators. Once quality passes, the score starts at 20 points and the remaining 80 points reward efficiency. T is the externally measured query latency, averaged within groups and then equally across groups. M is the sampled peak GPU memory above idle usage across preparation and query execution, including subprocesses, with a 1 GiB minimum. This is an external sampled measurement, not an allocator self-report. The immutable public starting implementation is measured on the same GPU, resource limits and requests, giving T_control and M_control with the same memory floor. Let C = (T/T_control) * (M/M_control). The score is `20 + 80 * clip(log(C/0.9) / log(0.5/0.9), 0, 1)`, and framework reward is score/100. Efficiency credit starts below C=0.9 and reaches full credit at C<=0.5, a twofold reduction in combined cost. Proportional latency and memory improvements contribute equally. CPU-only retrieval is allowed and uses the same 1 GiB memory floor.

### Timing and resource protocol

Final preparation has a hard 1,800-second limit and the same CPU, RAM and GPU allocation. It may restore frozen artifacts, compute training-only features, build an index and initialize persistent model services, but cannot train or tune a ranker or probe. Requests are delivered individually at concurrency one with a hard ten-second limit for each execution from delivery to completed output. The workload contains 100 unique requests, and requests may recur in different orders. Preparation still runs only once. This includes startup, token alignment, all forward/backward computation, projection, retrieval, reranking, serialization and GPU synchronization. Preparation services may retain fixed probe weights and training-only features, and are paused between requests. Any query-dependent error gradient, projection, score or ranking must be recomputed after that request arrives. Do not persist it to answer any later request, including a repetition with the same query ID. In-memory intermediates for the current request are allowed. Training-derived caches, entity candidate pools and fixed Top-10 training-ID lists per entity are allowed. During development you may collect development query features to fit a ranker; these cannot become final-request answer lookups.

Total logical task storage is 64 GiB, including public data/models, the submission, supplied and self-built caches, working files and temporary files; image/system packages are excluded. This limit applies throughout development, preparation and query execution. Do not bypass storage, timing, isolation or resource accounting, change filesystem permissions to reach restricted data, access credentials, or manipulate the grader/reward. An ordinary bug, timeout or low precision is not itself an integrity violation.

Logical storage accounting includes files that remain open after deletion, anonymous temporary files, and file-backed mappings retained after descriptors are closed, including those held by persistent preparation services. Hard links and multiple references to the same file count once. Storage inspection after a command has completed is excluded from measured query execution time.

## Hidden Test Overview

Final evaluation covers 100 distinct requests delivered individually after preparation; requests may recur in different orders. Development and final evaluation use disjoint entity pairs, modification sets and prompts.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, formats and use restrictions.

The coding agent's provider connection does not grant task-program API access. Follow this task's resource permissions; only the declared artifacts transfer to the separate verifier.
