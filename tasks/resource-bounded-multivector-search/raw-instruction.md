# Resource-bounded Multi-vector Retrieval

## Task Description

Build an offline CPU retrieval system for the complete 522,931-document BEIR Quora corpus using
fixed ColBERTv2 token vectors. Return up to 100 ranked document IDs and finite scores. Generate
candidates from the entire corpus; none are supplied. Minimize complete-workload query time while
retaining mean Recall@100 >= 0.99 against exhaustive original-vector MaxSim. Score query-time
improvement between a frozen strong baseline (zero) and measured faster reference (one). Algorithms,
compression, transformations, optional training, pruning, reranking and faster exact implementations
are unrestricted.

## Requirements

- Read-only `/task/data/public/corpus/{vectors.f32,offsets.i64,ids.json,config.json}`: 8,140,769 contiguous little-endian float32 token vectors, dimension 128. N+1 little-endian int64 offsets delimit each document. JSON IDs map corpus rows to original string document IDs.
- `/task/data/public/dev/`: identical layout for all 5,000 official development queries, each with 32 tokens; `truth.i32` is a 5000x100 little-endian int32 matrix of exact neighbor corpus rows, and `scores.f32` contains corresponding float32 scores.
- `/task/data/public/baseline/`: a frozen full-corpus OPQ/IVF/PQ index, token-to-document mapping and baseline metadata. Public source, rebuild command and executable baseline are under `/task/tools/baseline/`. This optional baseline is available in both phases and may be referenced without copying. Training or rebuilding is not required.
- `/task/tools/runtime_limits.py`: frozen baseline time `T_B`, faster reference time `T_U`, their relative speed target, minimum recall 0.99, a 600-second complete-query hard timeout, setup limits, hardware/runtime and hashes. Both anchors use all 10,000 queries with the same supervisor, eight cores, caps, JSONL boundary and five public warmups. Each verification first measures the pinned public baseline on the complete hidden workload, before any submitted code runs, with the same load/warmup/resource limits and a separate 600-second baseline query timeout. Its failure is infrastructure failure. Its timing `T_B_current` corrects current machine speed: `T_norm = T * T_B / T_B_current`. Baseline processes are killed and their temporary directory is made verifier-private before submission starts; no baseline hidden responses are exposed. The exact truth implementation remains `/task/tools/exact_search.py`, `/task/tools/maxsim.cpp` and `/task/tools/libmaxsim.so`; exhaustive runtime does not define the score.
- All 10,000 official test queries and their exhaustive answers are withheld until verification. Each current query is sent separately. Protocol query IDs are zero-based request sequence numbers, not original BEIR IDs.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. No internet, GPU, extra models/datasets, retrieval services or model APIs for the submission. The coding agent's provider connection grants no submission API access.

### Load interface

`/app/run.sh` is a persistent JSONL stdin/stdout process: exactly one response per request, flushed;
diagnostics only on stderr; each response at most 1 MiB. First request:
`{"op":"load","corpus":"/task/data/public/corpus","index":"/app/index","work_dir":"/work/runtime"}`.
Load artifacts and reply exactly `{"ok":true}`. Honor request paths for corpus, custom index and
writable work directory; a local self-test uses a different work directory. The supplied baseline
explicitly uses `/task/data/public/baseline` instead of a custom index. In verification UID 10001
runs the submission with `/app` and inputs read-only; only `work_dir` is writable for runtime files.
Process families are suspended between load, public warmup and the timed workload.

### Query and output contract

A query is `{"op":"query","query_id":0,"vectors":[...]}` with a 32x128 numeric array. Reply
`{"query_id":0,"results":[{"doc_id":"123","score":24.5}]}`. Return at most 100 items, string IDs,
finite numeric scores, descending score and equal-score ties by corpus row. Approximate scores are
allowed. Query failures may return an empty array and continue. No hidden input/answer access,
hard-coded answer mappings or verifier tampering; public truth is for development, not an answer
cache.

## Available Validation Data

Public self-check: `/opt/conda/bin/python /task/tools/check_submission.py --command /app/run.sh
--queries 100`. `--queries 5000` covers the whole dev split. It checks protocol and recall and
reports diagnostic timing; final quality and speed scoring use the complete held-out workload.
Compare the provided baseline and your implementation on identical public queries when tuning.

## Expected Artifacts

Put submitted code, newly built indexes, parameters and persistent caches under `/app`, with custom
index artifacts at `/app/index` and executable `/app/run.sh`. The frozen public baseline may be used
directly from its read-only path in both phases; copying it into `/app` is unnecessary. Include
`/app/README.md` with build command, observed build time and self-tests. Any build command is
allowed. All of `/app` transfers into a fresh verifier; dependencies installed elsewhere do not
transfer. Submit regular files/directories only, without symlinks, sockets or special files.

## Verification

### Metrics and failure handling

MaxSim is `sum_i max_j dot(q_i,d_j)` on original supplied FP32 vectors, using fixed exhaustive
reference accumulation and corpus-order ties. Human qrels do not define the answer.
`Recall@100 = |valid returned ID set intersect exact Top-100| / 100`. Duplicates count once, unknown
IDs do not hit, missing results miss. Over 100 results, malformed response, wrong query ID,
nonfinite score or wrongly sorted known IDs give that query zero. All 10,000 queries remain in the
denominator, including failed/unanswered queries. The complete workload must receive 10,000
responses, including empty responses for failed queries; exiting early cannot earn speed credit.
Loading/warmup failure, incomplete workload, memory/disk/development-time/600-second-query-time
violation, or mean Recall@100 < 0.99 gives overall zero. Otherwise normalized reward is
`clip((T_B-T_norm)/(T_B-T_U),0,1)`, where `0<T_U<T_B` and `clip(x,0,1)=min(1,max(0,x))`. Displayed
score is 100 times that reward, in [0,100]. `T_norm>=T_B` gives zero; `T_norm<=T_U` gives 100. The
600-second hard timeout applies to raw T, before normalization. No extra quality credit is given
once the 99% requirement is met. For illustration only, `T_B=100`, `T_U=50`, `T_B_current=120`,
`T=108` gives `T_norm=90` and 20 points; actual frozen seconds come from runtime_limits.py. Report
original Recall@100, runtime, baseline speedup, QPS, peak memory and artifact size separately.

### Timing and resource protocol

- Eight assigned CPU cores across the process family; query concurrency one, each query may use all eight cores; GPU unavailable.
- 16 GiB RAM includes vectors/index/cache/runtime/subprocesses. Swap disabled.
- 32 GiB storage includes public inputs, submission, indexes/parameters/caches, runtime temp files and diagnostics. Immutable installed environment and verifier-owned hidden data are excluded. A bounded filesystem reserves 512 MiB for diagnostics and incurs filesystem metadata overhead; `df` gives actual writable capacity. Write only to provided writable directories.
- 7,200 seconds total development, including coding-client setup, training, full-corpus transformations and all index construction. Trusted timing starts at environment readiness and ends at final artifact collection preparation. Artifacts must be ready when the agent ends. No additional offline build stage.
- Final startup/loading 120 seconds. Then first five public dev queries for warmup, 30 seconds total. These are separate from query time.
- T spans sending the first hidden query through receiving the final response: serialization/transport, transformations, candidate search, scoring, selection, query-dependent caching, output and background work all count. The complete-query hard timeout is 600 seconds. The measured baseline/reference times `T_B` and `T_U` are frozen before agent evaluation; the baseline is not slowed or chosen by the submission. Baseline, faster reference and submission use the same protocol, eight CPU cores, resource caps and five-query warmup. Test queries are never provided during setup; all computation after arrival counts.
- Missing assets/calibration or CPU mismatch is infrastructure failure. Another platform requires a full baseline recalibration before agent evaluation.

## Hidden Test Overview

All 10,000 official test queries and exhaustive answers are withheld until verification. The
submission receives one current query at a time; baseline hidden responses remain private.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
