# Budgeted Bimetric Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `budgeted-bimetric-retrieval` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | baseline-normalized mean nDCG@10 |
| Compute | 16 CPUs; 32 GiB RAM; 64 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 16200 s |

Improve retrieval over 250,000 NQ passages with 20 controlled expensive distances and two seconds per query.

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

A large candidate corpus must be searched with only 20 expensive distance calls and two seconds per query. Candidate generation and allocation of the limited oracle calls must improve ranking over the frozen baseline.

## Verification Explanation

The verifier averages nDCG@10 over all 3,452 hidden queries, including failed queries as zero, then normalizes improvement between the frozen baseline and full-corpus expensive-vector reference. Per-query oracle-call and time limits are enforced; build, resource and integrity failures give zero final reward. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task budgeted-bimetric-retrieval
python scripts/download_assets.py --task budgeted-bimetric-retrieval --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
64 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU.

Use a native Linux x86_64 Docker host with `/dev/fuse`, `mkfs.ext4`,
`dpkg-deb`, and root or sudo access. The standard launcher prepares fresh
bounded agent/verifier storage and the oracle socket directory, chooses
16 logical CPUs from its available affinity, and unmounts storage after the
run's containers exit. Backing images remain under
`jobs/.task-storage/budgeted-bimetric-retrieval/`.
Set `BIMETRIC_CPUSET` to preserve a particular 16-CPU allocation when reproducing
a run. See [bounded task storage](../../docs/evaluation.md#bounded-task-storage)
for host setup, permissions, recovery and caller-managed storage.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.

The independent verifier audit also requires `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` in that local configuration.
It uses `deepseek/deepseek-v4.1-flash`; only verifier egress to `openrouter.ai`
is allowed. These credentials are never passed to submitted commands.
The verifier protects the transferred trajectory, records the raw numerical
score, terminates candidate processes, and publishes reward only after a
healthy passing integrity audit. See `audit-status.json` for audit health.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task budgeted-bimetric-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/budgeted-bimetric-retrieval-codex-openrouter-luna-max"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/check_tasks.py tasks/budgeted-bimetric-retrieval
python scripts/download_assets.py --task budgeted-bimetric-retrieval --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

## References

None.
