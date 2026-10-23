# Training Error Tracing

## Task Description

Improve the supplied online training-data retriever so it uses less query time and GPU memory while
investigating erroneous language-model answers. For each actual generated answer and its marked
erroneous tokens, return up to ten IDs from the fixed training corpus that recover the records
affected by the corresponding controlled answer-entity replacement. Keep group-macro Precision@10 at
least 0.98 and every group at least 0.80, then reduce the combined query-latency and GPU-memory
cost. These modification labels do not establish that each returned record causally caused an
individual token. Text retrieval, fixed-model features or gradients, a retrieval ranker and mixed
methods are all allowed.

## Requirements

You have 14,400 seconds for implementation, feature/cache computation, retrieval-ranker training,
tuning and development evaluation, using one A100 40GB, 16 CPU cores and 64 GiB RAM. You may train a
separate retrieval ranker on public development labels during this stage. Do not update the fixed
probe or tokenizer, obtain the clean original Alpaca corpus for differencing, obtain hidden queries
before delivery, or use hidden labels, verifier files, author-only reference artifacts or prior test
answers. Do not obtain the omitted full BF16 base or producer checkpoint, or download, replace or
call an additional model, corpus or external task-model API. The coding agent's own authorized
provider calls are allowed; your retrieval program must run without external services.

### Query input

Each request is a JSON object with `id`, `instruction`, `input`, `generated_answer`, `input_ids`,
`prompt_token_count`, `target_token_indices` and `target_text`. The supplied IDs are the actual
prompt-plus-generation tokens, at most 512 tokens. Target positions are nonempty, unique, zero-based
positions in that sequence; the causal prediction for position j is at logits j-1. For model
computations, use the supplied IDs and preserve all target positions instead of introducing an
inexact re-tokenization or truncation. The query has no separate contamination-group label,
source-entity label or relevant-ID list. Hidden requests arrive individually after final
preparation. All delivered marked target-token IDs are covered by the supplied diagnostic output
rows; input IDs continue to use the complete original tokenizer vocabulary.

### Preparation and query commands

Prepare all runtime code and necessary frozen artifacts under `/app/submission/`. Only that
directory is transferred to a fresh verifier; the coding trajectory is also transferred for an
independent integrity review. Public fixed inputs and tools are mounted separately, read-only. Files
elsewhere in the development container, existing services and GPU state are not transferred. Include
executable `prepare.sh` and `run.sh`. The verifier calls `prepare.sh --data-dir /task/data
--model-dir /task/models --index-dir INDEX` once, then `run.sh --index-dir INDEX --query QUERY_JSON
--output OUTPUT_JSON --top-k 10` for each request. Both execute with the submission directory as
their working directory, as unprivileged UID/GID 10001. Submission files remain read-only; put
mutable working state under the fresh writable `INDEX` directory.

### Output contract

For each query, `run.sh` must exit successfully and write a regular UTF-8 JSON file of at most
65,536 bytes to `OUTPUT_JSON`, containing `query_id` exactly equal to the current query ID and `ids`
containing zero to ten ranked, unique IDs from `train.jsonl`. Output symlinks are rejected. A
shorter list is valid, with missing positions counted as misses. A malformed, missing or late
output, nonzero exit, incorrect query ID, duplicate/unknown IDs or more than ten IDs makes that
query's P@10 and P@5 zero and keeps it in the averaging denominator. Preparation failure or timeout,
total-resource violations, invalid submission metadata, fixed-probe updates or forbidden private
inputs invalidate the whole submission. Infrastructure failures are reported separately.

## Available Validation Data

The read-only training corpus is /task/data/train.jsonl, containing the actual 52,001 records with
id, instruction, input and output. Treat IDs as opaque, case-sensitive strings. /task/models/base/
supplies a compact diagnostic probe derived from Qwen/Qwen2.5-7B at revision
d149729398750b98c0af14eb82c78cfe92750796: all 28 decoder layers in the exact fixed NF4
double-quantized state, the complete original BF16 input embedding table, its exact tokenizer, and
64,439 original BF16 output rows selected using public training inputs only. Load it through
/task/tools/compact_probe.py::load_probe. The output rows retain original token IDs and are
losslessly compressed. They form a fixed diagnostic vocabulary, rather than a complete generative
output head. The erroneous generations were produced using this base with an adapter; that adapter
and the full BF16 checkpoint are not supplied solver inputs. Keep the supplied probe and tokenizer
parameters fixed. Selected probe components, inference quantization/dtype changes, CPU offloading
and gradients without optimizer updates are allowed. A separate retrieval ranker may be trained
during development. The Alpaca-derived training data remains subject to CC BY-NC 4.0
research/noncommercial terms; the included Apache-2.0 model license does not replace the dataset
terms.

Training-only fixed-base response-token losses are supplied as
/task/data/base-nll/base-token-nll.npz, and alternative token IDs as
/task/data/base-alternatives/base-token-alternatives.npz. Each archive contains one values array,
shaped 52,001 by 512 in training-record order; read it with numpy.load(...,
allow_pickle=False)["values"]. These arrays are losslessly identical to the original full-base
training diagnostics. Each directory contains row-ids.json and complete.json with exact
corpus/base/file hashes and the original uncompressed source hash; alternatives also identify the
matching NLL file. They were created before development without development/test errors or
contamination labels. Supplied preprocessing is excluded from development time; their supplied bytes
and any restored arrays count toward the respective storage/RAM budgets. They are full-base training
evidence, not a claim that the reduced output head yields full-vocabulary cross-entropy. An official
projected-gradient matrix and a producer-LoRA gradient pipeline are not supplied. Additional feature
computation, probe-gradient features and ranker fitting use your development budget. The public
starting retriever first checks confident training-derived lexical source evidence; remaining
requests use all 28 fixed probe layers with packed decoder weights on CPU, one layer at a time
transferred to GPU, CPU embedding/output rows and selected GPU output rows, and native JSON
transport. It precomputes tokenizer offsets and source pools from training inputs only;
source-cohort ties use training-token NLL. Its implementation is /task/tools/streamed_source.py. The
paired control already includes this memory optimization; further efficiency is measured relative to
it. Its code is the immutable paired control. A complete working submission is preinstalled under
/app/submission/. You may edit or replace it, or create another copy in an empty directory with
/opt/conda/bin/python /task/tools/build_starter.py --output EMPTY_DIR. When changing inference or
ranking, compare its outputs as well as development-label quality. Interface and probe
specifications are under /task/docs/.

Use `/task/data/dev-queries.jsonl` and `dev-labels.json` for development. They provide 50 actual
erroneous generations from five complete entity-pair groups, ten per group, with the modified
training IDs, source/error entities and associated query IDs. Hidden evaluation uses 100 actual
errors from ten other complete groups, ten per group. Each group has at least ten modified training
IDs. Development and test groups have disjoint entity pairs, modification sets and prompts, while
sharing the one fixed corpus and historical error-producing model. Several source groups
intentionally share an error entity within one split, with different relevant-ID sets. Use the
current query to distinguish them. A fixed list based only on the canonical error entity can score
at most 0.5 on the ten test groups; query-dependent methods can achieve much higher quality. The
five shared-target families stay intact for quality uncertainty estimates.

## Expected Artifacts

Also include `submission.json` with integer `schema_version` equal to 1, a nonempty `method` string,
a `configuration` object and a `frozen_artifacts` array. List trained rankers, precomputed
caches/lists and other frozen data artifacts. Each entry needs a `path` relative to the submission
directory, its actual `sha256`, and a nonempty `generation` string specifying how it was generated
and from which permitted inputs. Paths must stay inside the transferred directory. An empty artifact
array is valid if no such artifacts are used. Record enough configuration to reproduce your method
from public inputs.

## Verification

### Metrics and score

AP@10 here means average proportion: returned Top-10 IDs belonging to the query group's
modified-record set divided by ten. It is Precision@10, not Average Precision. Average within each
group and then give the ten groups equal weight to obtain Q; P@5 uses the first five results and
denominator five. Every repetition must reach Q >= 0.98 and every group P@10 >= 0.80; otherwise the
score is zero. Failed or missing requests remain in these denominators. Once quality passes, the
working-system milestone is 20 points and the remaining 80 points reward efficiency. For T, take the
median of each query's three measured times, average queries within groups, then average groups
equally. A verifier-owned NVML sampler measures the leased GPU's used memory throughout preparation
and all requests, including subprocesses, at nominal 10-ms intervals. Subtract that phase's idle
usage and let M be the larger of this sampled peak and 1 GiB. This is a sampled peak, not an
allocator self-report or a guarantee of capturing sub-sampling-interval transients. The fresh
verifier separately runs the immutable public starting implementation on the same GPU, limits and
requests after your processes have exited, obtaining T_control and M_control. Its preparation is
capped at 300 seconds and each control request at five seconds; a failed control is an
infrastructure failure. Let C = (T/T_control) * (M/M_control). The score is `20 + 80 *
clip(log(C/0.9) / log(R/0.9), 0, 1)`, and framework reward is score/100. Thus improvements smaller
than ten percent of combined cost receive no extra points, while a frozen reference ratio R gives
full credit. This is symmetric in proportional latency and memory changes. CPU-only retrieval is
allowed and uses the same 1-GiB accounting floor. R is fixed at 0.5: full credit means at least a
twofold reduction in the combined cost.

### Timing and resource protocol

Final preparation has a hard 1,800-second limit and the same CPU, RAM and GPU allocation. It may
restore frozen artifacts, compute training-only features, build an index and initialize persistent
model services, but cannot train or tune a ranker or probe. Each of the 100 unique hidden requests
is executed three times, in separately shuffled orders, at concurrency one with a hard ten-second
limit for each execution from delivery to completed output. Preparation still runs only once. This
includes startup, token alignment, all forward/backward computation, projection, retrieval,
reranking, serialization and GPU synchronization. Preparation services may retain fixed probe
weights and training-only features, and are paused between requests. Any query-dependent error
gradient, projection, score or ranking must be recomputed after that request arrives. Do not persist
it to answer any later request, including a repetition with the same query ID. In-memory
intermediates for the current request are allowed. Training-derived caches, entity candidate pools
and fixed Top-10 training-ID lists per entity are allowed. During development you may collect
development query features to fit a ranker; these cannot become final-request answer lookups.

The total supplied data/model assets are below 5,000,000,000 bytes (decimal 5 GB); no omitted full
checkpoint is mounted or bundled in the images. This asset-size target is separate from runtime
working storage and RAM. Total logical task storage is 64 GiB, including public data/models, the
submission, supplied and self-built caches, working files and temporary files; image/system packages
are excluded. The verifier checks logical usage during preparation and queries and at command
completion. Docker does not supply a kernel filesystem quota for this setting, so development usage
is also subject to resource/trajectory review. Do not bypass storage, timing, isolation or resource
accounting, change filesystem permissions to reach restricted data, access credentials, or
manipulate the grader/reward. The verifier's independent audit credentials are unavailable to
candidate programs. An ordinary bug, timeout or low precision is not itself an integrity violation.

## Hidden Test Overview

The verifier holds 100 actual errors in ten complete entity-pair groups, ten per group. Entity
pairs, modification sets and prompts are disjoint from public development. Queries arrive
individually after preparation and run in three separately shuffled repetitions.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
