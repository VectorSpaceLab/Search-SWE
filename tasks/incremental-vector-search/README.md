# Incremental Vector Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `incremental-vector-search` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | Time-gated logarithmic missed-neighbor reduction over public reference |
| Compute | 16 CPUs; 32 GiB RAM; 32 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 28800 s |

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

## Difficulty Explanation

The index must incorporate successive data additions and retain recall across five retrieval sizes. Index maintenance and query execution share strict stage budgets, so improvements must hold across the full sequence.

## Verification Explanation

The verifier replays incremental insertions and queries at five retrieval sizes. It counts missing exact neighbors, computes logarithmic error reduction over the fixed public reference, and aggregates the two collections. Each collection must pass its build, insertion, query and resource gates. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task incremental-vector-search
python scripts/download_assets.py --task incremental-vector-search --verify-only
python tasks/incremental-vector-search/prepare_data.py
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

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
bash scripts/run_task.sh --task incremental-vector-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/incremental-vector-search-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/check_tasks.py tasks/incremental-vector-search
python scripts/download_assets.py --task incremental-vector-search --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

## References

None.
