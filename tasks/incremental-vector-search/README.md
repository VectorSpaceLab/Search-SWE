# Incremental Vector Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `incremental-vector-search` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | Time-gated logarithmic missed-neighbor reduction over public reference |
| Compute | 16 CPUs; 32 GiB RAM; 32 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 86400 s |

Build an incremental vector index and maximize recall across five retrieval sizes under per-stage time budgets.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |
| 2026-11-05 | 1.0.0 | Portable CPU allocation, platform preparation, five-replay timing medians and restored public validation |

## Difficulty Explanation

The index must incorporate successive data additions and retain recall across five retrieval sizes. Index maintenance and query execution share strict stage budgets, so improvements must hold across the full sequence.

## Verification Explanation

For each collection, the verifier performs five independent complete incremental replays at five retrieval sizes, with fresh state and a fresh process for each replay. Each build, insertion and stage/K query gate uses its five-sample median; query quality comes from the replay corresponding to that cell's median time. A missing timing after timeout counts as infinity. Invalid execution or resource violations invalidate the collection. It counts missing exact neighbors, computes logarithmic error reduction over the fixed public reference, and aggregates the two collections. Each collection must pass its build, insertion, query and resource gates. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

The task consumes 28 finished files listed in `assets.json`: 18 public corpus/validation files under `data/` and 10 hidden test files under `tests/data/`. The normal `search-swe run` command restores and verifies all of them. Only the public subdirectories are mounted into the agent; hidden files are mounted into the verifier and trusted preparation container. No original Parquet shards, sampling scripts, external hidden-test archive or data conversion are required.

For standalone restoration, use `python scripts/assets/download_assets.py --task incremental-vector-search`. All 28 public and verifier-only inputs are published in the official dataset at revision `13c218a82ae222dc65a4eeb070e4f46602b5cadb` and restored through the pinned asset manifest.

### Automatic platform preparation

Use the normal `search-swe run` or `scripts/evaluation/run_task.py` entrypoint. The launcher automatically calls `tools/prepare_task.py` before Harbor starts, so preparation does not consume the agent's 120-minute budget. There is no manual preparation command or platform-directory setup for the evaluator.

The helper verifies all fixed inputs, makes the public reference programs and data readable by UID 10001, and runs a disposable offline container with 16 logical CPUs, 32 GiB RAM and no swap. It uses the runner's `--cpu-set` allocation, or selects 16 available CPUs; no CPU model or fixed CPU IDs are prescribed. The supplied images and isolation support Linux x86_64 with Landlock ABI >= 1 and seccomp.

On the first run for a platform, the helper regenerates numerical targets if needed, measures one complete replay of the exact reference and one of the public PQ reference per collection, then freezes query budgets and baseline quality. Formal submission evaluation still runs five times and uses median timings. The query gate remains 10% of the exact reference time. Baseline quality is measured under generous query ceilings, with `baseline_within_query_budget` indicating whether it also meets the candidate gate. The logarithmic score formula and fixed event workload are unchanged.

The first calibration can take several hours and is bounded by a 24-hour preparation timeout. The first exact-reference replays measured on this host total about 1.7 hours for both collections, plus roughly four minutes of PQ query work and preparation overhead. Each reference is measured once; this estimate is not a guarantee for another machine. Cached runs verify hashes and skip those measurements. Preparation is serialized to prevent concurrent writers; use an allocation without competing workloads for timing comparisons.

Completed caches live under ignored `tests/platform/<cache-key>/`. A cache key includes hardware, CPU allocation, kernel and numerical runtime, input manifest, and calibration/grading/reference code. A reboot alone does not invalidate the cache. Every reuse checks the output hashes. Changed inputs are rejected until restored; changed hardware/runtime/code receives a new cache, and incomplete or corrupted output is never reused. Each run receives one immutable cache path shared by its agent and verifier, so another allocation's preparation cannot replace its limits.

Public limits and current-runtime public validation are mounted read-only into both phases; prepared hidden targets are verifier-only. Failed preparation stops before the coding agent is launched. Direct container startup checks the supplied preparation and cannot silently reuse a different platform's time limits.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
32 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/evaluation/run_task.sh --task incremental-vector-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/incremental-vector-search-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/incremental-vector-search
python scripts/assets/download_assets.py --task incremental-vector-search --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

## References

- [Source provenance and usage terms](SOURCES.md)
- [Validation evidence and unrun layers](VALIDATION.md)
