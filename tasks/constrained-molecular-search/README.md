# Constrained Molecular Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `constrained-molecular-search` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | Macro mean Recall@10000; public proportional-budget Recall@279 |
| Compute | 16 CPUs; 32 GiB RAM; 64 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 10500 s |

Recover the truly feasible top 10,000 compounds from a complete molecular library under a two-second query deadline.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-25 | 1.0.0 | Added initial task |

## Difficulty Explanation

The retriever must recover the true feasible top compounds, combining molecular constraints with ranking over the complete library. A two-second query deadline makes candidate pruning and exact feasibility checks interact.

## Verification Explanation

The verifier checks the returned compounds against the true feasible Top-10,000 from the complete library and computes macro mean Recall@10000. Preparation and query limits are enforced separately. The final numerical reward also requires a healthy passing integrity audit. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/assets/download_assets.py --task constrained-molecular-search
python scripts/assets/download_assets.py --task constrained-molecular-search --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
64 GiB storage. Agent development has
21600 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases require one GPU. Use `--gpu-device` to select the same
host GPU for both phases.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
Also configure `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` for the independent
`deepseek/deepseek-v4.1-flash` integrity judge. These credentials are injected only
into the verifier. Its service timeout includes a separate 3600-second audit
allowance; submission phase limits remain unchanged. A positive final reward
requires a successful accepting audit of the protected trajectory and submission.
Inspect `audit-status.json`, `audit.json` and `reward-details.json` alongside the
deterministic report; missing or unhealthy audits cannot produce a positive reward.

Invoke the standard entrypoint directly:

```bash
bash scripts/evaluation/run_task.sh --task constrained-molecular-search --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/constrained-molecular-search-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/constrained-molecular-search
python scripts/assets/download_assets.py --task constrained-molecular-search --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## References

- [Task reference](https://proceedings.mlr.press/v306/pedawi26a.html).
- [APEX source dataset](https://zenodo.org/records/17455955), CC BY 4.0.
- [APEX source checkpoints](https://zenodo.org/records/17456522), CC BY-NC 4.0.

## Repeated measurements

Each request is measured five times in five complete passes. Prepare runs once. After preparation, generated artifacts become read-only; use TMPDIR for query-time writes. Each pass starts a fresh Searcher process and a cleared scratch directory, while initial preparation and all loads still share the 3600-second allowance. The median of the five complete-response times must be at most 2.0 seconds. Each individual measurement has a 3.0-second execution cap. All five measurements must return valid ID lists; otherwise the request scores zero. For a request passing these checks and the median limit, its recall is the arithmetic mean of the five recalls. Empty or small feasible sets remain supported and are used as unscored diagnostics.

The integrity review runs independently three times. Its reported value is the arithmetic mean of the three binary decisions. A positive task reward requires all three reviews to accept the submission. A missing, failed or malformed review is an evaluation infrastructure failure.
