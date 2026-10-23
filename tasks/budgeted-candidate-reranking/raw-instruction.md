# Budgeted Candidate Reranking

## Task Description

Build a runnable reranking strategy selecting at most ten IDs from each supplied BM25 Top-100
passage pool. Optimize mean linear-gain nDCG@10 under one fixed local model budget. No strategy is
installed in `/app`; optional read-only simple baseline examples are in `/task/baselines`. No
training or particular algorithm is required, and those examples may be replaced entirely.
Pointwise, pairwise, listwise and mixed methods, snippet extraction, local lightweight features and
fusion with initial scores are allowed. Any of the 100 candidates may appear in the result,
including those never sent to the model.

## Requirements

Use only supplied data and the supplied fixed model. Do not use external datasets, models, APIs,
retrieval/reranking services, hidden judgments, hard-coded query/document answer maps or precomputed
evaluation answers. Genuine general reranking logic is required. Do not fine-tune, quantize, replace
or modify model weights, tokenizer, chat template, generation settings, trusted code or accounting.
Do not bypass the trusted model entry point or manipulate verifier resources/results.

### Query and model-service interfaces

`run.sh` is invoked without arguments once per query. Its stdin receives one newline-terminated JSON object:

```json
{
  "type": "query",
  "query_id": "...",
  "query": "...",
  "candidates": [
    {
      "doc_id": "...",
      "text": "...",
      "bm25_score": 1.0,
      "rank": 1
    }
  ],
  "token_budget": 2048,
  "output_weight": 4
}
```

The actual candidate array has 100 entries in original BM25 order; ranks are 1-based,
IDs/queries/text are strings. Stdout is exclusively newline-terminated JSON messages, each at most
256 KiB including newline; stderr is diagnostic output limited to 1 MiB per query. Flush each stdout
message. While awaiting a response, read stdin again.

Request generation with:

```json
{
  "type": "generate",
  "messages": [
    {
      "role": "user",
      "content": "..."
    }
  ],
  "max_new_tokens": 1,
  "logprob_tokens": [
    "Yes",
    "No"
  ],
  "candidate_ids": [
    "..."
  ]
}
```

`messages` is 1–64 objects with exactly string `role` (`system`, `user`, `assistant`) and `content`.
`max_new_tokens` is a required integer 1–512. Optional `logprob_tokens` is an array of at most 32
strings, each encoding as exactly one tokenizer token; default empty. Optional `candidate_ids` is a
distinct list of current-pool IDs, default empty, used only as diagnostic declarations, never as
relevance evidence. No other request fields are supported. The supervisor replies:

```json
{
  "type": "generation",
  "text": "...",
  "input_tokens": 123,
  "output_tokens": 1,
  "spent_tokens": 127,
  "remaining_tokens": 1921,
  "first_token_logprobs": {
    "Yes": -0.1,
    "No": -3.0
  }
}
```

`text` omits special tokens; billing includes all generated tokens including EOS. Log probabilities
concern the first next-token distribution, regardless of which token was generated.

The same request with `type` set to `count` tokenizes and returns

```json
{
  "type": "count",
  "input_tokens": 123,
  "reserved_cost": 127,
  "remaining_tokens": 2048
}
```

This performs no model forward and incurs no charge. This exact token preview does not execute
inference. Its response wait counts toward the same 90-second trusted-response limit. No separate
socket, API server or client-startup command is needed; the evaluator starts the trusted service and
mediates every request over the pipes. Requests from child processes or queued concurrently are
serialized through this one stream and share the query's supervisor-owned state. Reconnection, a new
client or child process cannot reset it. Malformed requests or a `generate` reservation exceeding
remaining credit end the query with zero quality. A `count` preview may exceed remaining credit so
that the strategy can shorten the proposed prompt without executing it.

### Output contract

Finish with:

```json
{
  "type": "result",
  "ids": [
    "doc-id",
    "another-id"
  ]
}
```

Use exactly these two fields. `ids` must be a JSON array of at most ten distinct string IDs from the
current candidate pool, in descending desired relevance. No scores are required; missing positions
have zero gain. Empty results are valid. Do not add candidates or depend on future test inputs. The
result terminates the process tree; the strategy need not wait for an extra acknowledgment.

## Available Validation Data

All 43 judged TREC DL2019 queries, fixed candidates and complete public qrels are
`/task/data/public.jsonl.gz` and `/task/data/public-qrels.json`. The test has all 54 judged DL2020
queries with independent runtime-hidden labels. These are public benchmarks; hidden means isolated
at runtime. Only the current test query and its candidates are delivered, after deployment/warmup.
Candidate generation uses Anserini 1.4.0 BM25 k1=0.9, b=0.4 over the full 8,841,823-passage index,
independently of relevance labels. Candidate IDs, original text, float BM25 scores and original
rank/order are frozen. No queries are removed or positives inserted. MS MARCO's noncommercial
research terms apply.

Run `/opt/conda/bin/python /task/runtime/evaluate.py --submission /app/submission --output
/app/dev-report` as root in the development environment. It uses the same model, budget, protocol,
isolation and query-time semantics on the public queries. Read its `report.json`, query stderr and
trusted `model.stderr`. It reports raw quality and trusted per-call accounting rather than a
normalized test score. You may choose any development procedure within the same resource rules; no
mandatory strategy implementation is supplied.

## Expected Artifacts

Work under `/app`; treat `/task` as read-only. Read `/task/docs/environment.md` and
`/task/docs/available_resources.md`. Submit executable `/app/submission/run.sh`, regular
`/app/submission/deployment.json` (at most 4096 bytes), and any implementation/support files below
`/app/submission`. Only that directory is transferred. It must be self-contained with installed
dependencies; symlinks, special files and downloads are not supported. No package installation,
custom loading code or callback runs in the trusted model process. `deployment.json` supports only
`attention` (`sdpa` default, or `eager`) and `cpu_threads` (integer 1–16, default 8); an empty
object is valid. Only Transformers 5.15.1 / PyTorch 2.9.0+cu130, BF16, single-request inference and
the supplied Qwen/Qwen3-1.7B revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e are supported.
Thinking is disabled with the frozen chat template and decoding is greedy. No sampling, custom stop
sequences or persistent prefix/KV cache. Optional first-token log probabilities use the same
generation, with no separate unmetered model forward.

## Verification

### Metrics and score

Let Q be mean nDCG@10 over all 54 tests using official 0–3 linear gains and standard log2 discounts.
Unjudged IDs have gain 0; each IDCG uses the complete official qrels, not a selected subset or
candidate-only normalization. B is the frozen best whole-test mean among BM25 Top-10 and simple
dev-selected fixed head-reranking baselines under this same model/budget. U is the frozen
candidate-oracle whole-test mean, computed by ideally sorting the original 100 by judgment using
that same full-qrels IDCG. Neither B nor U is chosen per query or changed for the submission.
Candidate pools without positives are retained as zero in Q, B and U. B and U must be valid and U>B;
missing/degenerate anchors fail closed as task infrastructure errors. Score is `100 *
clip((Q-B)/(U-B),0,1)` and Harbor reward is score/100. Copying or worsening the best simple baseline
gives zero. The verifier also reports Q/B/U, initial recall, actual tokens, diagnostic declared
candidate coverage, load/warmup/strategy/inference time and resource peaks. No LLM judge is used.

### Timing and resource protocol

The verifier validates hashes, loads its own fixed model and reconstructs only those supported
options. Deployment including hash validation/loading has 600 seconds; public-only `Hello.` warmup
has 60 seconds. Failure of either gives zero for the whole task. The container has a 256-task PID
limit covering the trusted runtime and strategy descendants. The model runtime owns the GPU; final
strategy code runs as UID 10001 without GPU access, privileges or network. `/app/submission` is
read-only; the strategy's fresh current directory `/work` is its only writable area (apart from
`/dev/null` and protocol pipes). A new strategy process/work directory is created per query. Saved
public-data preprocessing must be packaged inside the submitted directory. The strategy and all
descendants are terminated after its result or failure.

The agent has 7200 seconds for development, 16 CPUs, 32 GiB aggregate RAM and 40 GiB task storage,
including fixed checkpoint, submitted files and generated caches/artifacts. The base image,
framework logs and automatic submission-transfer staging are outside task-storage accounting. `/app`
is a 24 GiB tmpfs, whose pages also count toward the shared 32 GiB RAM limit; fixed checkpoint plus
all submitted/work caches still have a 40 GiB total limit. One NVIDIA A100-SXM4-40GB is provided
with a 24 GiB total device-memory cap; the trusted backend caps its PyTorch allocator at 22 GiB to
leave context/driver headroom. The model, backend, strategy and subprocesses share the CPU/RAM
limits; do not launch additional models. Both task phases have no network and no task API keys. The
separate verifier has 7200 seconds overall.

Per query `sum(input_tokens + 4 * output_tokens) <= 2048`. All
chat-template/system/query/candidate/repeated/intermediate context counts. Logical cache hits would
be charged in full; this backend has no cross-request inference cache or batching. Input plus four
times the maximum requested output is atomically reserved before execution; a request whose
reservation does not fit is not executed and the query fails. After success the reservation is
settled using actual output length. Executed failed requests retain their complete reservation. No
unused budget transfers between queries. There is no additional call-count or processed-document
limit and no reward for speed, call count or model coverage.

The strategy has 1.0 cumulative second of wall time per query, including interpreter startup, input
reading, selecting/snipping, constructing prompts, sorting and output. Only pure waiting for the
trusted component is excluded: the supervisor first stops and verifies the whole strategy tree
before starting the excluded interval and resumes it after the reply. Work done by any descendant
before that stop still counts. Local work cannot overlap the excluded interval. The cumulative
trusted-response time (including all count/generate requests and their tokenization/queue time) is
limited to 90 seconds per query. Exceeding either query deadline, token budget, invalid output,
execution/inference failure or a protocol error gives that query zero, retaining it in the
denominator. Deployment/warmup failure, exceeding aggregate RAM/VRAM/storage, or an actual
integrity/entry-point violation gives zero for the whole task. The verifier uses root-owned trusted
processes, filesystem permissions, Landlock, seccomp and process-tree control; the strategy cannot
read hidden labels, alter trusted state, use the GPU or write rewards.

## Hidden Test Overview

The verifier uses all 54 judged DL2020 queries and complete official relevance judgments. Only the
current query and its fixed BM25 Top-100 candidates are sent to the strategy after
deployment/warmup.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
