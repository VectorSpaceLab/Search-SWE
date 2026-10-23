# constrained-molecular-search

Recover the truly feasible top 10,000 compounds from a complete molecular library under a two-second query deadline.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task constrained-molecular-search
python scripts/download_assets.py --task constrained-molecular-search --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document.

## Run

The task allocates 16 CPU cores, 32 GiB RAM and
64 GiB storage. Agent development has
21600 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases require one A100 40GB GPU. Reserve an idle device and configure
both Docker phases to expose that same device explicitly. Verify the actual
container mapping before running; a host CUDA_VISIBLE_DEVICES value alone is
insufficient. Release the reservation after all run containers/processes exit.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
Also configure `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` for the independent
`deepseek/deepseek-v4.1-flash` integrity judge. These credentials are injected only
into the verifier. Its service timeout includes a separate 1200-second audit
allowance; submission phase limits remain unchanged. A positive final reward
requires a successful accepting audit of the protected trajectory and submission.
Inspect `audit-status.json`, `audit.json` and `reward-details.json` alongside the
deterministic report; missing or unhealthy audits cannot produce a positive reward.

Invoke the standard entrypoint directly:

```bash
bash scripts/run_task.sh --task constrained-molecular-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/constrained-molecular-search-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

## Validate the package

```bash
python scripts/check_tasks.py tasks/constrained-molecular-search
python scripts/download_assets.py --task constrained-molecular-search --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.
