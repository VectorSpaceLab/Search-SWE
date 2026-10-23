# Training Error Tracing

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `training-error-tracing` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | quality-gated paired query-latency and GPU-memory cost |
| Compute | 16 CPUs; 16 GiB RAM; 64 GiB storage; 1 GPU |
| Agent / verifier time limits | 14400 s / 8400 s |

Improve a working training-record retriever beyond training-text routing and layer-streamed fixed-base fallback.

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

The retriever must identify influential training records beyond the provided routing and fixed-base fallbacks. Quality gates must hold while reducing paired query latency and GPU-memory cost.

## Verification Explanation

The verifier measures the proportion of modified training records among the returned Top-10, requiring mean quality of at least 0.98 and at least 0.80 for every group on every repetition. Passing quality earns a 20-point milestone; the remaining credit measures paired latency and sampled GPU-memory improvement over a fresh run of the immutable public control. Harbor stores the displayed score divided by 100. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task training-error-tracing
python scripts/download_assets.py --task training-error-tracing --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

### Run

The task allocates 16 CPU cores, 16 GiB RAM and
64 GiB storage. Agent development has
14400 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases require one A100 40GB GPU. Use `--gpu-device` to select the same
host GPU for both phases.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task training-error-tracing --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/training-error-tracing-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/check_tasks.py tasks/training-error-tracing
python scripts/download_assets.py --task training-error-tracing --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

The verifier Compose service grants `SYS_PTRACE` and `CHECKPOINT_RESTORE` so the trusted supervisor can account for open-unlinked and memory-mapped task files. The host kernel/runtime must support these capabilities. Candidate commands drop all capability sets. Storage inspection errors fail closed; unit and real descriptor/mapping regressions are in `tests/test_storage_accounting.py` and can run in a disposable verifier without a GPU.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

None.
