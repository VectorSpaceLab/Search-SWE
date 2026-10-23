# Instruction Following Embedding

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `instruction-following-embedding` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | Harmonic mean of three positive subset p-MRR values (otherwise zero), gated by six nDCG@10 checks |
| Compute | 16 CPUs; 32 GiB RAM; 32 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 7200 s |
| Dataset | FollowIR Robust04/Core17/News21; topic-disjoint 20-group development and 84-group test partition |

Adapt a compact E5-large-v2 query adapter within a 512KiB deployment budget while retaining the fixed base document space.

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

A query-side adapter must follow retrieval instructions while retaining the fixed document embedding space. The 512 KiB deployment budget, three-subset harmonic mean and six quality gates require improvements that transfer across subsets.

## Verification Explanation

The verifier measures instruction-sensitive p-MRR on three subsets and uses their harmonic mean when all three are positive. Six nDCG@10 retention gates require at least 90% of the fixed relevance reference. Reward normalizes the resulting metric between frozen anchors after model, resource and integrity checks. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task instruction-following-embedding
python scripts/download_assets.py --task instruction-following-embedding --verify-only
python tasks/instruction-following-embedding/prepare_inputs.py
python tasks/instruction-following-embedding/prepare_inputs.py --verify-only
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

Both phases require one A100 40GB GPU. Use `--gpu-device` to select the same
host GPU for both phases.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task instruction-following-embedding --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/instruction-following-embedding-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/check_tasks.py tasks/instruction-following-embedding
python scripts/download_assets.py --task instruction-following-embedding --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

None.
