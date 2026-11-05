I need a local model that can make decisions across different tasks, such as choosing a message's intent, making a yes/no judgment, or assigning an ordered rating. Each request provides a text or JSON state, the questions to answer, and their answer menus. Please build the decision system around the supplied Qwen3-0.6B model so it can also handle task schemas absent from the supplied examples.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime and available files. Labeled examples are at `/task/data/examples.jsonl`, and the starting model is at `/task/models/Qwen3-0.6B`. Network access and external APIs are unavailable. Do not use external datasets, additional pretrained weights, hidden examples or labels, precomputed answers, or hard-coded input-to-answer mappings.

You have 6 hours for development, with one GPU, 16 CPU cores, 32 GiB RAM and 100 GiB storage.

Place the complete submission under `/app/submission`, including executable `start.sh` and `run.sh` and every file needed at runtime. Only this directory is transferred to the separate verifier; installed packages and live processes from development are not transferred. The supplied model and resource documents remain available there, but `examples.jsonl` does not. `/task` is read-only. The verifier runs your submission as a non-root user with `/app/submission` read-only; use the supplied runtime directory for generated files and the requested output path for results.

The verifier first starts the system with:

```bash
/app/submission/start.sh --runtime-dir /path/to/runtime
```

Finish model loading and initialization and return status zero within 120 seconds. The runtime directory starts empty and its path may vary. Resident processes may remain available for the next call. Hidden requests become available only after startup completes.

The complete request batch is then passed through:

```bash
/app/submission/run.sh \
  --runtime-dir /path/to/runtime \
  --requests /path/to/requests.jsonl \
  --output /path/to/results.jsonl
```

Read `request_id`, `state`, and `questions` from each input record; the question format matches the examples. Write one JSONL record per request, such as `{"request_id":"request-id","answers":{"question-id":"selected-label"}}`. Answer every question: for `choice`, return an exact criterion key string; for `noul`, a JSON Boolean; for `score`, an integer indexing the ordered criteria list from zero. Cover every request exactly once, in any output order.

All 4,200 requests must finish within 240 seconds after startup, including input processing, inference and output writing. Return status zero after writing the complete output. Startup or inference timeouts, command failures, missing or invalid output, or integrity violations receive score zero.

Quality is evaluated by exact answer accuracy on seven equally sized hidden datasets. Maximize this accuracy to improve your final score.
