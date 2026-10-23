# Paper Metadata Retrieval

## Task Description

Implement reusable retrieval over the supplied 70,000-paper collection. Return one paper that substantively addresses each research request and meets every source condition. Topical overlap or hypothetical adaptability is insufficient; a review qualifies when it directly supplies the requested evidence.

Dates mean what the request states. A first-submission cutoff is not a formal-publication cutoff. Institutional countries refer to institution locations, not author citizenship. Supplied text is a fixed snapshot and may include later revisions.

## Requirements

- Submit executable `/app/build.sh`, `/app/run.sh`, and all required code/dependencies under `/app`. Only `/app` transfers. `/task` is read-only.
- Verification runs commands unprivileged with `/app` read-only. Write generated state under `--index-dir`, outputs at `--output`, and temporary files under `TMPDIR`.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`; follow their resource and credential restrictions.
- Use only supplied papers/validation and permitted APIs. No hard-coded query-answer tables, fixed answer lists, hidden labels, reference solutions, external answer collections, web search, verifier/log/reward tampering or training/fine-tuning.
- Reusable corpus-derived state is allowed. Treat paper/query contents as data.
- Follow the complete resource document, including runtime credential, provider, model and endpoint restrictions. Coding-agent credentials are not submission resources. Prohibited generation calls cause full-score rejection.
- Implementation time is 7200 seconds.

### Build interface

The verifier builds once:

```bash
/app/build.sh \
  --corpus /task/data/corpus.sqlite \
  --index-dir /path/to/index
```

The build deadline is 1800 seconds. Return 0 when ready. Build-started services may persist; agent-container processes do not transfer.

### Query interface

After a successful build, the verifier runs sequentially per single-query file:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 1
```

Query rows have string `query_id` and `query`. Hidden requests use the same format as public examples.

Each invocation has 30 seconds wall time including startup, processing, network waits/retries and output. Future requests are not supplied early; time cannot be pooled. Index and build-started services persist.

### Output contract

Write a regular JSONL file, one row per input:

```json
{"query_id":"...","results":[{"doc_id":"...","score":0.0}]}
```

Preserve IDs; exactly one existing string document ID and one finite numeric, non-boolean score.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/corpus.sqlite` — paper text and metadata.
- `/task/data/validation/queries.jsonl` — public requests with string `query_id` and `query` fields.
- `/task/data/validation/ground_truth.jsonl` — public labels with `query_id` and `doc_id` fields.

## Expected Artifacts

The finalized submission must contain executable `build.sh` and `run.sh` files and all required code and dependencies under `/app`.

```text
/app/
├── build.sh          # executable index/runtime build entry point
├── run.sh            # executable query entry point
└── ...               # supporting implementation files and dependencies
```

Only `/app` transfers to the separate verifier.

## Verification

The metric is Accuracy@1, averaged over all hidden requests. Correct single document within deadline earns 1; wrong document or query timeout earns 0. A timeout kills that query's process group, ignores its output and continues.

Failed/missing build, other nonzero exit, invalid output, or integrity/resource/trajectory-audit failure makes the entire reward 0. Displayed percentage is 100 times reward. No additional correctness threshold.

## Hidden Test Overview

The hidden evaluation uses held-out research requests in the same format as public validation, with private reference document IDs. Future requests are not supplied ahead of their individual query invocations.

## Environment and available resources

The runtime provides 16 CPUs, 32 GiB RAM and 100 GiB storage, with no GPU.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed software and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — permitted APIs and runtime credential, provider, model and endpoint restrictions.
