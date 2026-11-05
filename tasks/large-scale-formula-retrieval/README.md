# Large Scale Formula Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `large-scale-formula-retrieval` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | nDCG_prime |
| Compute | 2 CPUs; 4 GiB RAM; 64 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 67800 s |
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

The verifier builds once and runs five independent serving passes, with fresh processes/runtime directories, identical warmup and fixed query order. For each query, it scores the response associated with the median elapsed time; failed or invalid attempts rank after valid attempts within 50 ms. Fewer than three successful attempts gives that query zero. The response is selected by timing, never by relevance score. The verifier sorts instances by descending score, maps them to visual IDs, deduplicates and computes nDCG prime using the complete judgments. It averages across all 76 hidden questions, including failures. Final reward also requires one healthy, accepting integrity audit. See the [verification contract](raw-instruction.md#verification) and [current validation record](VALIDATION.md).

Candidate deadlines remain 3,600 seconds for building, 120 seconds for each load and 30 seconds for each warmup. The maximum five-pass restart path permits 60,619 seconds of candidate work. The primary supervisor has 66,000 seconds for those stages, cleanup and scoring; the audit wrapper has 1,200 seconds, finalization has 30 seconds and the outer verifier has 67,800 seconds. Normal runs build only once; the larger supervisor budget accommodates the existing per-query recovery policy.

Harbor enforces the agent deadline and transfers the available submission to the
verifier. Agent command completion is not a separate scoring gate: the verifier
checks the submitted build and service normally. Trusted development OOM evidence
remains mandatory, and a recorded memory violation still makes the score zero.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/assets/download_assets.py --task large-scale-formula-retrieval
python scripts/assets/download_assets.py --task large-scale-formula-retrieval --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Model cards,
licenses and data-use restrictions are described in the resource document and
[SOURCES.md](SOURCES.md).

Public corpus files restore directly under `data/`; the five public queries and their judgments restore as `data/validation/queries.jsonl` and `data/validation/qrels.tsv`. Existing official HF files, immutable revisions, sizes and hashes are reused without changing data. Historical dataset filenames retain `public/dev/`; those remote filenames do not determine the local restored layout. Host FUSE tools are cached outside public inputs, under `jobs/.task-storage/large-scale-formula-retrieval/.tools/` by default.

### Run

The task allocates 2 CPU cores, 4 GiB RAM and
64 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

This task uses no GPU. Development and the timed final build may optionally use the OpenRouter/Jina APIs listed in [available resources](environment/docs/available_resources.md). Configure `OPENROUTER_API_KEY` and/or `JINA_API_KEY` for the services used; these submission credentials are separate from coding-agent and judge credentials. Follow the [submission API key profile](../../docs/evaluation/submission-models.md). Model-weight and extra-dataset/package downloads are prohibited. Loading, warmup and queries remain offline. API waits count toward the existing time budgets, and stored outputs count toward the existing storage limits.

Use a native Linux x86_64 Docker host with `/dev/fuse`, `mkfs.ext4`,
`dpkg-deb`, Landlock support, and root or sudo access. The standard launcher prepares fresh
bounded agent, verifier and serving storage, chooses 2 logical CPUs from its
available affinity, and unmounts storage after the run's containers exit.
Backing images remain under `jobs/.task-storage/large-scale-formula-retrieval/`.
Set `FORMULA_CPUSET` to preserve a particular 2-CPU allocation when reproducing
a run. See [bounded task storage](../../docs/evaluation/runtime.md#bounded-task-storage)
for host setup, permissions, recovery and caller-managed storage.

Both Compose overlays require the selected CPU variable rather than assuming particular host CPU numbers. The standard launcher supplies it automatically. The 40 MiB serving filesystem is an enforced disk quota, not an optional tmpfs allocation; retain it on other supported hosts. CPU selection portability does not guarantee identical 50 ms performance across machines.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
Also configure `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` for the independent
`deepseek/deepseek-v4.1-flash` integrity judge. These credentials are injected only
into the verifier. Its service timeout includes a separate 1200-second audit
allowance; submission phase limits remain unchanged. A positive final reward
requires a successful accepting audit of the protected trajectory and submission.
The audit runs as UID 10002 with a filtered environment and filesystem restrictions. It can read the submission and a protected trajectory copy, write its own scratch/output, and cannot read hidden inputs or modify grading reports. Aggregate, raw and normalized criterion decisions must agree. Missing, malformed or inconsistent audits are infrastructure failures, while a confirmed rejection is a valid zero.
Inspect `audit-status.json`, `audit.json` and `reward-details.json` alongside the
deterministic report; missing or unhealthy audits cannot produce a positive reward.

Invoke the standard entrypoint directly:

```bash
bash scripts/evaluation/run_task.sh --task large-scale-formula-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/large-scale-formula-retrieval-codex-openrouter-luna-max"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval
python scripts/assets/download_assets.py --task large-scale-formula-retrieval --verify-only
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
gates. `scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval`, shell syntax
and diff whitespace checks also passed. The instruction, input assets and
numeric scoring are unchanged.

Container isolation/storage tests and evaluation of archived submissions were
not run in this revision; they remain follow-up validation. No coding-model run
or judge API call was made.

## References

- [Task reference](https://aclanthology.org/2026.findings-acl.1277/).

- [Data, model and method provenance](SOURCES.md).
