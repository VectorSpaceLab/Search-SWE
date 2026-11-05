# Instruction Following Embedding

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `instruction-following-embedding` |
| Version | 1.1.0 |
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
| 2026-11-05 | 1.1.0 | Median query timing over five measurements; disk workspaces; GPU count-only requirement; restored public data; calibration metadata synchronized |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

A query-side adapter must follow retrieval instructions while retaining the fixed document embedding space. The 512 KiB deployment budget, three-subset harmonic mean and six quality gates require improvements that transfer across subsets.

## Verification Explanation

The verifier measures instruction-sensitive p-MRR on three subsets and uses their harmonic mean when all three are positive. Six nDCG@10 retention gates require at least 90% of the fixed relevance reference. Reward normalizes the resulting metric between frozen anchors after model, resource and integrity checks. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

Documents are prepared once. Each query/instruction version is measured five times through the complete fixed encoding and ranking path, with a 1-second median limit. The median measurement supplies the ranking; timeouts stay in the sample population, and malformed output still invalidates the pair. This task has no answer/evidence LLM judge; its compliance audit is unchanged.

The primary wrapper allows 5,000 seconds, including up to 3,600 seconds for preparation and 840 one-second query measurements (84 groups × 2 versions × 5). The remaining primary time covers setup, reporting and bounded worker recovery. Primary/audit/finalization wrappers plus kill grace total 7,015 seconds (5,000 + 15 + 1,950 + 15 + 30 + 5), leaving 185 seconds within the 7,200-second verifier limit. `/app` and `/tmp` use disk; the runtime checks their logical file sizes plus mounted data/models against 32 GiB. Artifact collection is a separate phase with its existing 600-second limit.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/assets/download_assets.py --task instruction-following-embedding
python scripts/assets/download_assets.py --task instruction-following-embedding --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions. Keep verifier inputs outside agent mounts. The three required corpora restore to `data/corpus/{robust04,core17,news21}.jsonl`; processed training data and public validation groups restore to `data/train.jsonl` and `data/validation/dev-groups.json`. Runtime restoration does not download raw preparation inputs or require a preprocessing step. Source and license information is recorded in `DATA_SOURCES.md`.

### Run

The task allocates 16 CPU cores, 32 GiB RAM and
32 GiB storage. Agent development has
7200 seconds. Final-stage limits and accounting are
specified in the task contract; the verifier service timeout also includes its
trusted setup and checks.

Both phases use one NVIDIA GPU with support for the fixed CUDA/BF16/SDPA runtime. Use `--gpu-device` to select the same
host GPU for both phases. GPU model and memory capacity are not task requirements; changing hardware still requires runtime and timing validation.

Configure `AGENT_OPENROUTER_API_KEY` through the existing ignored `.env` or
authorized process environment, following the repository README.
The independent verifier audit also needs `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL` as documented by the repository runner. Credentials
are not submission inputs.

Invoke the standard entrypoint directly:

```bash
bash scripts/evaluation/run_task.sh --task instruction-following-embedding --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/instruction-following-embedding-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/instruction-following-embedding
python scripts/assets/download_assets.py --task instruction-following-embedding --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device compatible with the task runtime. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## References

None.
