# Video-Moment Search

## Task Description

Build a search system that locates the time interval matching a natural-language description within a specified video.

## Requirements

### Resource limits and workload

- The environment has 8 CPU cores, 32 GiB RAM, 100 GiB storage and one 40 GiB GPU.
- Development has a six-hour budget.
- The supplied encoders are fixed.
- An optional temporal/scoring component may have up to 5 million trainable parameters and use up to 45 minutes of training.
- Per request, at most 64 candidate intervals may receive learned or token-level fine scoring; inexpensive frame-level screening and boundary proposals are allowed.
- Index construction has up to 60 minutes, and query calls follow the workload below.
- Calls may be repeated with different input files.

- Process each request independently.
- Data, models and documentation are read-only.
- Put all other required runtime files under `/app`.
- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`.

- The system must handle workloads of up to 500 requests in 2 calls of at most 250 requests.
- Each call has an independent 2,700-second allowance; time used by one call does not reduce another.
- Completed valid JSONL rows remain usable if a query call times out; missing or malformed rows are unsuccessful.
- A failed query command other than a timeout invalidates that call.

### Execution and file permissions

- During verification, build and query commands run as a non-root user with `/app` and supplied inputs read-only.
- The passed index directory already exists and is writable during construction, but its parent directory is not writable.
- Create build files and temporary directories inside the index directory or the supplied `TMPDIR`; do not create siblings or rename the index directory itself.
- The completed index becomes read-only for retrieval.
- Query results, caches and temporary files belong in the writable output directory or the supplied `TMPDIR` and `XDG_CACHE_HOME`.
- Honor the passed paths rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Create executable `/app/build.sh` and `/app/run.sh` and their supporting files under `/app`:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /work/index
```

### Query interface

```bash
/app/run.sh \
  --index-dir /work/index \
  --queries /work/input/queries.jsonl \
  --output /work/output/results.jsonl
```

### Input and output contract

Each input JSONL row contains `query_id`, `video_id` and `description`, the original natural-language description. For each input row return the same `query_id` and numeric `start` and `end` values in seconds. Return exactly one nonempty interval whose endpoints belong to that video's supplied grid. Write diagnostics to stderr.

## Available Validation Data

The supplied videos are represented by frozen frame vectors at `/task/data/corpus/`. Its `records.jsonl` contains `video_id`, `duration` in seconds, `feature_path` and `grid_path`. Paths are relative to that directory. Each feature row corresponds to one successive interval between adjacent time-grid endpoints. The video vectors were generated with CLIP ViT-B/32. The same fixed image and text encoder is available at `/task/models/clip/`; raw video files are not supplied.

Public training requests and interval labels are at `/task/data/training/queries.jsonl` and `/task/data/training/labels.jsonl`. Five validation requests and their labels are at the corresponding paths under `/task/data/validation/`. Labels contain `query_id`, `video_id` and `windows`, a list of acceptable start/end pairs. The remaining requests and labels are not provided.

You may use the public examples to implement and check the complete build and query path during development. Include all required implementation files under `/app` so the system runs after a fresh start with the supplied inputs.

## Expected Artifacts

Submit executable `/app/build.sh` and `/app/run.sh` together with every implementation file and learned parameter required at runtime under `/app`.

```text
/app/
├── build.sh
└── run.sh
```

## Verification

After development, Harbor transfers the declared artifacts to a separate verifier and evaluates the system on the held-out split. The verifier checks the following items:

1. **Task and resource compliance.** The submission must use the supplied inputs and permitted resources, follow stage isolation, and avoid hidden labels or hard-coded evaluation answers.
2. **Executable behavior.** The required commands must follow the interfaces, filesystem permissions and time limits above and support the specified repeated calls.
3. **Output validity.** Results must satisfy the task-specific schema, identifiers, bounds and ordering rules. The failure and timeout behavior follows the contracts above.
4. **Search quality.** Let x be the best IoU between the predicted interval and the acceptable reference intervals. Its utility is u(x) = 0.7 * mean(I[x >= 0.5], I[x >= 0.7], I[x >= 0.9]) + 0.3 * x. Divide that utility by the best utility attainable with one legal interval on the supplied time grid. Average within each source, then equally across sources.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
