# Sketch-and-Text Image Search

## Task Description

An image search request may contain a rough sketch of only part of the desired composition and a description of the complete scene. Build a system that uses these inputs to find the matching artwork in the supplied gallery.

## Requirements

### Resource limits and workload

- You have six hours, 8 CPU cores, 32 GiB RAM, 100 GiB storage and one 40 GiB GPU.
- The supplied encoders are fixed; scoring or fusion components may use up to 30 minutes of adaptation.
- The build command has 3,600 seconds.
- The system must handle up to 1,260 requests in three calls of at most 420 requests, with an independent 1,800-second allowance for each call.
- Completed valid JSONL rows remain usable if a call times out; missing or invalid rows are unsuccessful.
- A command failure other than timeout invalidates that call.

- Data, models and documentation are read-only.
- Generate the index at the passed index path.
- Include required runtime files and learned weights under `/app` so the system works after a fresh start with the supplied gallery, model and current queries.
- Training and validation labels are not runtime indexing inputs.
- Use the local resources described in `/task/docs/available_resources.md` and read `/task/docs/environment.md`.
- Aim to place the matching artwork among the first three results, especially first, for both broad and detailed descriptions.

### Execution and file permissions

- During verification, build and query commands run as a non-root user with `/app` and supplied inputs read-only.
- The passed index directory already exists and is writable during construction, but its parent directory is not writable.
- Create build files and temporary directories inside the index directory or the supplied `TMPDIR`; do not create siblings or rename the index directory itself.
- The completed index becomes read-only for retrieval.
- Query results, caches and temporary files belong in the writable output directory or the supplied `TMPDIR` and `XDG_CACHE_HOME`.
- Honor the passed paths rather than writing to `/app` or assuming a writable system temporary directory.

### Build interface

Provide executable `/app/build.sh` and `/app/run.sh`, together with their implementation and learned files under `/app`. The build interface is:

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

### Input and output contract

Each input JSONL row contains `query_id`, `description` and `sketch_path`. The sketch path is an absolute path to the current sketch image.

Return the same `query_id` and a `results` list of at most ten distinct gallery images. Each result contains `image_id` and a finite numeric `score`, in nonincreasing score order. Write diagnostics to stderr. Process each sketch-description pair independently; descriptions and results from other requests are not additional context. Computations depending only on the gallery or an image may be cached.

## Available Validation Data

The gallery is at `/task/data/corpus/`. Each row of `records.jsonl` contains `image_id` and `image_path`, with paths relative to that directory. Original gallery images are available. Local image and text encoder weights are at `/task/models/clip/`. Sketches are partial views; they need not depict every element mentioned in the description.

Training pairs and their relevance labels are in `/task/data/training/queries.jsonl` and `/task/data/training/labels.jsonl`. Public validation pairs are at the corresponding paths under `/task/data/validation/`. Labels contain `query_id` and `qrels`, a mapping of gallery image IDs to relevance labels. You may use these inputs to develop and check the system.

A development-only permissions check is available at `/task/docs/check_runtime.py`; it runs your scripts under these permissions without scoring or reading labels. For example, use:

```bash
/opt/conda/bin/python /task/docs/check_runtime.py build \
  --corpus /task/data/corpus \
  --index-dir /work/runtime-check/index
```

For a query check, use the `query` stage with that index, a public `--queries` path and an `--output` path under `/work/runtime-check/output/`.

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
4. **Search quality.** Per-query raw quality is 0.5 * Recall@3 + 0.5 * MRR@3. Scores are averaged within each of the three description levels, then equally across the levels. The interface accepts up to ten results, but only the first three affect the metric.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.
