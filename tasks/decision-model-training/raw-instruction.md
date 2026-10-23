# Decision Model Training

## Task Description

Build a local decision model based on Qwen3-0.6B. Given a text or JSON state and
the questions and answer menus for a request, return the appropriate decisions.
Handle categorical choices, Boolean decisions, and ordinal ratings, including
task schemas absent from the supplied examples.

## Requirements

- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`.
- `/task` is read-only. Network access and external APIs are unavailable. Do not
  use external datasets, additional pretrained weights, hidden examples or
  labels, precomputed answers, or hard-coded input-to-answer mappings.
- The development budget is 6 hours.
- Submit all runtime files under `/app/submission`, including executable
  `start.sh` and `run.sh`. Only this directory is transferred. Installed packages
  and running processes from development are not transferred.
- The separate verifier retains the model and resource documents but not
  `examples.jsonl`. The submission runs as a non-root user with
  `/app/submission` read-only. Write runtime files under the supplied
  `--runtime-dir` and results to `--output`.

### Startup interface

The verifier invokes:

```bash
/app/submission/start.sh --runtime-dir /path/to/runtime
```

The initially empty runtime directory may vary. Finish model loading and
initialization and return exit status zero within 120 seconds. Resident
processes can remain available for the following call. No hidden requests are
available before startup completes.

### Inference interface

After successful startup, the verifier invokes:

```bash
/app/submission/run.sh \
  --runtime-dir /path/to/runtime \
  --requests /path/to/requests.jsonl \
  --output /path/to/results.jsonl
```

Input JSONL records contain `request_id`, `state`, and `questions`, using the
same question format as the examples.

The complete batch of 4,200 requests has a 240-second limit after startup.
Input processing, inference and output writing count toward this limit.
Batching is allowed. Return exit status zero after the complete output is written.

### Output contract

Output one JSONL record per request:

```json
{"request_id":"request-id","answers":{"question-id":"selected-label"}}
```

Return every question's answer exactly once: `choice` is an exact criterion key
string, `noul` a JSON Boolean, and `score` an integer indexing the ordered
criteria list from zero. Cover every request exactly once; output order is free.

## Available Validation Data

Labeled examples are available at `/task/data/examples.jsonl`. Requests use the
same question format as these examples.

## Expected Artifacts

The finalized submission must contain all runtime files under `/app/submission`,
including executable `start.sh` and `run.sh`:

```text
/app/submission/
├── start.sh          # executable model-loading and initialization entry point
├── run.sh            # executable batch-inference entry point
└── ...               # supporting implementation files and dependencies
```

Only this directory is transferred to the separate verifier.

## Verification

Hidden evaluation uses exact answer accuracy, averaged over seven equally sized
datasets. Maximize this accuracy. Startup or inference timeout, command failure,
missing or invalid output, or an integrity violation results in score zero.

## Hidden Test Overview

The hidden evaluation contains 4,200 requests across seven equally sized
datasets, including task schemas absent from the supplied examples. Hidden
requests are unavailable before startup completes, and `examples.jsonl` is not
retained in the separate verifier.

## Environment and available resources

The runtime provides one NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM and
100 GiB storage. The starting model is `/task/models/Qwen3-0.6B`.

Read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed runtime and execution environment.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local resources and the offline policy.
