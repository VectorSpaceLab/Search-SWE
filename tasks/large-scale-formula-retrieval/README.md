# Large Scale Formula Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `large-scale-formula-retrieval` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | nDCG_prime |
| Compute | 2 CPUs; 4 GiB RAM; 64 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 19800 s |
| Public queries | 5 |
| Hidden queries | 76 |

Retrieve relevant formulas from the complete ARQMath v3 corpus with 34 MiB prepared artifacts in a 40 MiB serving filesystem and 50 ms CPU queries.

The complete task contract is in [raw-instruction.md](raw-instruction.md).
The coding agent receives [instruction.md](instruction.md),
[available resources](environment/docs/available_resources.md), and
[environment instructions](environment/docs/environment.md).
Those documents specify the submission interface, allowed inputs, scoring,
failure behavior and public self-check commands.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Added initial task |

## Difficulty Explanation

The complete formula corpus must be searchable with only 34 MiB of prepared artifacts, a 40 MiB serving filesystem and 50 ms CPU queries. Representation, indexing and ranking must balance mathematical relevance with these limits.

## Verification Explanation

The verifier maps returned formula instances to visual IDs, deduplicates them and computes nDCG prime using the official judgments. It averages across all 76 hidden questions, including failures, with compact-serving storage and runtime limits enforced. Final reward also requires the integrity audit to pass. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

Harbor enforces the agent deadline and transfers the available submission to the
verifier. Agent command completion is not a separate scoring gate: the verifier
checks the submitted build and service normally. Trusted development OOM evidence
remains mandatory, and a recorded memory violation still makes the score zero.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/download_assets.py --task large-scale-formula-retrieval
python scripts/download_assets.py --task large-scale-formula-retrieval --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document and
[SOURCES.md](SOURCES.md).

### Run

The task allocates 2 CPU cores, 4 GiB RAM and
64 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU.

On the Linux Docker host, `/dev/fuse` and `mkfs.ext4` must be available.
Prepare fresh bounded storage for each run, then set `FORMULA_CPUSET` to
2 available logical CPU IDs on a supported CPU. Use a unique `RUN_ID`:

```bash
python tasks/large-scale-formula-retrieval/tools/prepare_storage.py --run-id RUN_ID
export FORMULA_STORAGE_ROOT="$PWD/jobs/.task-storage/large-scale-formula-retrieval/RUN_ID"
```

```bash
export FORMULA_JOB_ROOT="$PWD/jobs/large-scale-formula-retrieval-codex-openrouter-luna-max-RUN_ID"
install -d -m 0700 "$FORMULA_JOB_ROOT"
```

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
bash scripts/run_task.sh --task large-scale-formula-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "${FORMULA_JOB_ROOT}"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

After every container/process for this run has exited, unmount its storage:

```bash
python tasks/large-scale-formula-retrieval/tools/prepare_storage.py --run-id RUN_ID --unmount
```

### Validate the package

```bash
python scripts/check_tasks.py tasks/large-scale-formula-retrieval
python scripts/download_assets.py --task large-scale-formula-retrieval --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

### Local checks (2026-10-28)

From `tasks/large-scale-formula-retrieval/tests`,
`python -m unittest test_development test_scoring test_ipc_cleanup test_integrity_gate -v`
passed all 25 tests. These cover development-gate acceptance without agent completion logs, retained
OOM rejection, missing/malformed/private memory evidence, scoring and integrity
gates. `scripts/check_tasks.py tasks/large-scale-formula-retrieval`, shell syntax
and diff whitespace checks also passed. The instruction, input assets and
numeric scoring are unchanged.

Container isolation/storage tests and evaluation of archived submissions were
not run in this revision; they remain follow-up validation. No coding-model run
or judge API call was made.

## References

- [Task reference](https://aclanthology.org/2026.findings-acl.1277/).

- [Data, model and method provenance](SOURCES.md).
