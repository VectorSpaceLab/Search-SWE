# Composed Image Search

## Task Description

A user starts with a photograph and describes a change they want, such as a different arrangement or a different quantity of an object. Build an image search system that finds matching photographs in the supplied gallery while retaining the parts of the reference that the request leaves unchanged.

## Requirements

### Resource limits and workload

- You have two hours, 8 CPU cores, 32 GiB RAM and 100 GiB working storage and one 40 GiB GPU.
- The build command has 3,600 seconds.
- The system must handle up to 4,400 requests in two calls of at most 2,200 requests, with an independent 14,400-second allowance for each call.
- At most 100 candidate images per request may undergo additional query-dependent visual inspection.
- Corpus-wide global-vector screening and gallery-only preprocessing are allowed.
- The local model and permitted APIs are available as described in `/task/docs/available_resources.md`; also read `/task/docs/environment.md`.

- Treat data, models and documentation as read-only.
- The submitted `/app` files must work in a fresh environment with the supplied inputs, using the passed index and output paths for generated files.
- Query calls may be repeated after a build.
- Completed valid JSONL rows remain usable if a call times out; missing or invalid rows are unsuccessful.
- A command failure other than timeout invalidates that call.
- Aim to return the requested images near the start of each ranking across the supplied requests.

### Execution and file permissions

- During verification, build and query commands run as a non-root user.
- The implementation under `/app` and the supplied inputs are read-only.
- The passed index directory already exists and is writable, but its parent directory is not writable.
- Create build files, caches and temporary directories inside that index directory or the supplied `TMPDIR`; do not create sibling directories or rename the index directory itself.
- The index persists and remains writable across query calls.
- Write results at the passed output path, whose parent directory is writable.
- Honor `TMPDIR` and `XDG_CACHE_HOME` rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Provide executable `/app/build.sh` and `/app/run.sh` with their supporting files under `/app`. The build interface is:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /work/index
```

### Query interface

The query interface is:

```bash
/app/run.sh \
  --index-dir /work/index \
  --queries /work/input/queries.jsonl \
  --output /work/output/results.jsonl
```

Honor the supplied paths.

### Input and output contract

Each input JSONL row contains `query_id`, `reference_image_id`, `modification` and `shared_concept`. The reference belongs to the gallery. `shared_concept` provides an additional description when available and can be empty; the reference and modification still define the request.

Return one JSONL row for each request with its unchanged `query_id` and a `results` list of at most 50 distinct gallery images. Each result contains `image_id` and a finite numeric `score`, ordered by nonincreasing score. Exclude the reference image. Write diagnostics to stderr.

## Available Validation Data

The gallery is at `/task/data/corpus/`. Each row of `records.jsonl` contains `image_id` and `image_path`; paths are relative to the corpus directory. Gallery images are supplied. Local image and text encoder weights are available at `/task/models/clip/`.

Public requests and relevance labels are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Labels map each `query_id` to `qrels`, which may contain several matching images. You may use these examples to develop and check the system.

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
4. **Search quality.** Raw quality uses average precision and recall to measure the ranking and coverage of annotated matching images. The applicable cutoffs, query groups and equal-weight aggregation are defined in [README.md — Search Quality](README.md#search-quality).

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
