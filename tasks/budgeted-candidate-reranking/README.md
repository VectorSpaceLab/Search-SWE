# Budgeted Candidate Reranking

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `budgeted-candidate-reranking` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | nDCG@10 improvement normalized by fixed-candidate headroom |
| Compute | 16 CPUs; 32 GiB RAM; 40 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 9000 s |
| Dataset | MS MARCO passage; all 43 judged TREC DL2019 public queries and all 54 judged DL2020 test queries |

Improve fixed BM25 Top-100 passage reranking with a metered, frozen local Qwen3-1.7B model.

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

The candidate pool and local model are fixed. The system must allocate a small weighted token budget across candidate comparisons and improve ranking while respecting strategy and inference deadlines.

## Verification Explanation

The verifier measures mean linear-gain nDCG@10 over all 54 hidden queries and normalizes improvement between a frozen baseline and the fixed-candidate oracle. Candidate pools, full-qrels normalization and model/token budgets remain fixed. A healthy passing trajectory audit gates the numerical reward. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task budgeted-candidate-reranking
python scripts/download_assets.py --task budgeted-candidate-reranking --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
40 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases require one A100 40GB GPU. Use `--gpu-device` to select the same
host GPU for both phases.

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
bash scripts/run_task.sh --task budgeted-candidate-reranking --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/budgeted-candidate-reranking-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/check_tasks.py tasks/budgeted-candidate-reranking
python scripts/download_assets.py --task budgeted-candidate-reranking --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

None.
