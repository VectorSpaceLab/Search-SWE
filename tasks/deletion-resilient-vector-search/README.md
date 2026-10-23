# Deletion Resilient Vector Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `deletion-resilient-vector-search` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | normalized log-error reduction * (0.8 + 0.2 memory efficiency) |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 86400 s |

Maintain graph-vector search quality and reclaim memory through 100 deletion stages on SIFT1M and GIST1M.

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

## Difficulty Explanation

Repeated deletions affect graph connectivity, recall and memory use. The implementation must retain search quality while reclaiming memory across 100 deletion stages on two vector collections.

## Verification Explanation

The verifier replays 100 deletion stages on each dataset, measuring Recall@10 and process memory. Reward combines normalized logarithmic error reduction over the frozen tombstone reference with memory efficiency. Build, mutation, query and resource limits apply throughout the sequence. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task deletion-resilient-vector-search
python scripts/download_assets.py --task deletion-resilient-vector-search --verify-only
python tasks/deletion-resilient-vector-search/tools/prepare_inputs.py --split learn
python tasks/deletion-resilient-vector-search/tools/prepare_truth.py --dataset sift
python tasks/deletion-resilient-vector-search/tools/prepare_truth.py --dataset gist
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
100 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU.

On the Linux Docker host, `/dev/fuse` and `mkfs.ext4` must be available.
Prepare fresh bounded storage for each run, then set `DELETION_CPUSET` to
16 available logical CPU IDs on a supported CPU. Use a unique `RUN_ID`:

```bash
python tasks/deletion-resilient-vector-search/tools/prepare_storage.py --run-id RUN_ID
export DELETION_STORAGE_ROOT="$PWD/jobs/.task-storage/deletion-resilient-vector-search/RUN_ID"
```

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task deletion-resilient-vector-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/deletion-resilient-vector-search-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

After every container/process for this run has exited, unmount its storage:

```bash
python tasks/deletion-resilient-vector-search/tools/prepare_storage.py --run-id RUN_ID --unmount
```

### Validate the package

```bash
python scripts/check_tasks.py tasks/deletion-resilient-vector-search
python scripts/download_assets.py --task deletion-resilient-vector-search --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

## References

None.
