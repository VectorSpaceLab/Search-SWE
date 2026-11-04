# Protein Text Bidirectional Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `protein-text-bidirectional-retrieval` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | Equal-weight mean of per-dataset strict reciprocal-top1 paired success fractions |
| Compute | 16 CPUs; 16 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 3600 s / 130000 s |

Learn compact 64-dimensional protein/text embeddings and maximize strict reciprocal-top1 pair recovery under online latency and submission limits.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-11-04 | 1.0.0 | Added initial task |

## Difficulty Explanation

Compact protein and text representations must recover the same pair as the top result in both directions. The 64-dimensional space, deployment size and online latency limits constrain both representation learning and search.

## Verification Explanation

Author-side regressions are in `authoring/tests/` and are excluded from the verifier image. Run `python -m unittest discover -s tasks/protein-text-bidirectional-retrieval/authoring/tests -p 'test_*.py'` from the repository root. Container-specific cases require a disposable verifier environment.

A pair succeeds only when its independently executed protein-to-text and text-to-protein queries both rank the counterpart first. The verifier averages those success fractions equally across the two datasets. All official pairs remain in the denominator, and deployment, latency, resource and integrity gates apply. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

[Validation evidence](VALIDATION.md) distinguishes the deployment limits from measured results and records the remaining need for a trial under the current 16 GiB memory limit. It also documents the public/runtime boundary and checks for the documentation cleanup.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/assets/download_assets.py --task protein-text-bidirectional-retrieval
python scripts/assets/download_assets.py --task protein-text-bidirectional-retrieval --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model provenance,
licenses and data-use terms are described in [SOURCES.md](SOURCES.md).

### Run

The task allocates 16 CPU cores, 16 GiB RAM and
100 GiB storage. Agent development has
3600 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases require one GPU; the verifier does not restrict its model or memory capacity. Use `--gpu-device` to select the same
host GPU for both phases.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/evaluation/run_task.sh --task protein-text-bidirectional-retrieval --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/protein-text-bidirectional-retrieval-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/protein-text-bidirectional-retrieval
python scripts/assets/download_assets.py --task protein-text-bidirectional-retrieval --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## References

- [Task reference](https://aclanthology.org/2024.acl-long.324/).

- [Data, model and method provenance](SOURCES.md).
