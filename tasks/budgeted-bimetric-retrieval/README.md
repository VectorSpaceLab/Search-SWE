# budgeted-bimetric-retrieval

Improve retrieval over 250,000 NQ passages with 20 controlled expensive distances and two seconds per query.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task budgeted-bimetric-retrieval
python scripts/download_assets.py --task budgeted-bimetric-retrieval --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

## Run

The task allocates 16 CPU cores, 32 GiB RAM and
64 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU.

On the Linux Docker host, `/dev/fuse` and `mkfs.ext4` must be available.
Prepare fresh bounded storage for each run, then set `BIMETRIC_CPUSET` to
16 available logical CPU IDs on a supported CPU. Use a unique `RUN_ID`:

```bash
python tasks/budgeted-bimetric-retrieval/tools/prepare_storage.py --run-id RUN_ID
export BIMETRIC_STORAGE_ROOT="$PWD/jobs/.task-storage/budgeted-bimetric-retrieval/RUN_ID"
```

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task budgeted-bimetric-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/budgeted-bimetric-retrieval-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

After every container/process for this run has exited, unmount its storage:

```bash
python tasks/budgeted-bimetric-retrieval/tools/prepare_storage.py --run-id RUN_ID --unmount
```

## Validate the package

```bash
python scripts/check_tasks.py tasks/budgeted-bimetric-retrieval
python scripts/download_assets.py --task budgeted-bimetric-retrieval --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.
