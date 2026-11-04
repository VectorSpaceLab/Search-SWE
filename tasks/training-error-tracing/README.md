# Training Error Tracing

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `training-error-tracing` |
| Version | 1.0.0 |
| Authors | jianlyu |
| Primary metric | quality-gated paired query-latency and GPU-memory cost |
| Compute | 16 CPUs; 16 GiB RAM; 64 GiB storage; 1 GPU |
| Agent / verifier time limits | 14400 s / 11400 s |

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
| 2026-11-04 | 1.0.0 | Added initial task |

## Difficulty Explanation

The retriever must identify influential training records beyond the provided routing and fixed-base fallbacks. Quality gates must hold while reducing paired query latency and GPU-memory cost.

## Verification Explanation

The verifier measures the proportion of modified training records among the returned Top-10, requiring mean quality of at least 0.98 and at least 0.80 for every group on every repetition. Passing quality earns a 20-point milestone; the remaining credit measures paired latency and sampled GPU-memory improvement over a fresh run of the immutable public control. Harbor stores the displayed score divided by 100. See the [verification contract](raw-instruction.md#verification) for exact formulas, thresholds and failure handling.

### Restore inputs

Run from the repository root using the repository's existing Python environment:

```bash
python scripts/assets/download_assets.py --task training-error-tracing
python scripts/assets/download_assets.py --task training-error-tracing --verify-only
```

[assets.json](assets.json) fixes file sizes, hashes and source revisions or bundled
restoration paths. Keep verifier inputs outside agent mounts. Data provenance and
license notices are recorded below for maintainers.

### Run

The task allocates 16 CPU cores, 16 GiB RAM and
64 GiB storage. Agent development has
14400 seconds. Final-stage limits and accounting are
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
bash scripts/evaluation/run_task.sh --task training-error-tracing --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output "jobs/training-error-tracing-codex-openrouter-luna-max-RUN_ID"
```

Inspect the resulting agent trajectory, submission and verifier report under the
job directory. The score alone does not distinguish an invalid submission from
an infrastructure error.

### Validate the package

```bash
python scripts/validation/check_tasks.py tasks/training-error-tracing
python scripts/assets/download_assets.py --task training-error-tracing --verify-only
```

Build both `environment/Dockerfile` and `tests/Dockerfile` with their respective
directories as build contexts. Run the public helper and verifier with the task's
resource controls and mounts. Tests that exercise process isolation or GPU
enforcement belong in disposable task containers, not the shared host.

`authoring/tests/test_public_runtime.py` covers input alignment, retrieval routing, public quality checks, metadata hashes, submission-user readability and isolation of the control copy. Run it in a disposable verifier container with the task source mounted read-only at `/package` and the standard `/task/runtime` and `/task/starter` mounts: `/opt/conda/bin/python -m unittest discover -s /package/authoring/tests -p test_public_runtime.py -v`. It uses synthetic inputs and mocks model inference; it does not replace a full GPU trial or efficiency calibration.

The verifier Compose service grants `SYS_PTRACE` and `CHECKPOINT_RESTORE` so the trusted supervisor can account for open-unlinked and memory-mapped task files. The host kernel/runtime must support these capabilities. Candidate commands drop all capability sets. Storage inspection errors fail closed; unit and real descriptor/mapping regressions are in `authoring/tests/test_storage_accounting.py` and can run in a disposable verifier without a GPU by setting `SEARCH_SWE_RUN_ISOLATION_TESTS=1`.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation/runtime.md#gpu-device-selection) explains selection and per-run records.

## Maintainer notes

### Data construction and probe provenance

The hidden workload has 100 queries in ten groups, ten queries per group. The groups form five shared-error-entity families. Each family has two groups with disjoint relevant-record sets, so a single fixed Top-10 list chosen only by error entity has group-macro Precision@10 at most 0.5. The families stay together for quality uncertainty estimates. These are construction and shortcut-analysis facts, not solver instructions; the agent only needs to know that the current request can distinguish different sources sharing an erroneous entity.

The corpus derives from Alpaca revision `dce01c9b08f87459cf36a430d809084718273017`, corresponding to Stanford `alpaca_data.json` at `761dc5bfbdeeffa89b8bff5d038781a4055f796a`. One record without retained response loss was excluded. The fixed probe derives from Qwen/Qwen2.5-7B revision `d149729398750b98c0af14eb82c78cfe92750796`: all 28 decoder layers in serialized NF4/double-quantized state, complete BF16 input embeddings and 64,439 original BF16 output rows. The output rows come from training text, training alternative-token IDs and vocabulary tokens sharing a nonempty token surface with those alternatives; no error-query labels or source-target group mappings select them. The supplied asset-size target is below 5,000,000,000 bytes and is separate from the runtime storage allowance.

The Alpaca derivative uses CC BY-NC 4.0 terms. The included model's Apache-2.0 license does not replace the data terms.

### Package layout

- `environment/starter/` is the single source for the working retriever. The agent image copies it into editable `/app/submission`; both phases mount the original read-only at `/task/starter`, and the verifier copies that original into a private directory before freezing and running its paired control.
- `environment/runtime/` contains only the shared training-input loader, compact-probe API, native query client and public quality checker. Both phases mount it read-only at `/task/runtime`.
- `environment/docs/` documents the installed environment, allowed resources and public interfaces.
- `assets/model/` and `assets/diagnostics/` contain five bundled metadata files. `assets.json` restores them into the unchanged model/data paths with the same file hashes. Metadata is not mounted as a separate runtime directory.
- `tests/` contains the private verifier, hidden data and regression tests. Optional alternative retrievers, their training scripts and unused adapter configuration are not part of the task package.

The starter's `submission.json` records hashes for its three source/entry-point files and four shared runtime files. Update these hashes when changing those files. The verifier's control is copied from the read-only canonical starter and frozen by the existing runner, never copied from the agent's edited `/app/submission`.

### Scoring parameters and validation limits

The current score is defined by `tests/efficiency_metrics.py` and `tests/data/evaluation-config.json`, with the precision-only development helper at `environment/runtime/score_dev.py`. There is no additional public reward implementation or obsolete quality-only B/U normalization.

| Parameter | Role in the fixed task design |
| --- | --- |
| Q >= 0.98; every group P@10 >= 0.80 | Quality acceptance gates on every repetition. |
| 20 quality points; 80 efficiency points | Credit split after all quality gates pass. |
| C = 0.9 | Efficiency-credit threshold; improvements within 10% receive no extra credit. |
| Reference cost ratio 0.5 | Full-credit target: halve the paired latency-memory product. |
| 1 GiB GPU-memory floor | Finite memory accounting for low-GPU-memory or CPU-only systems. |

These are frozen task-design parameters. The repository currently lacks a complete empirical calibration report for the quality gates, credit split and 10% threshold, including a measured noise distribution under the current protocol. The parameter name `noise_ratio` is not evidence that such a distribution was measured. Record independent reference/candidate runs and resource measurements before claiming empirical calibration or full-credit reachability; documentation cleanup does not provide that evidence.

### Runtime implementation

The verifier discovers the allocated GPU UUID and samples GPU memory at nominal 10-ms intervals. It runs the immutable control after candidate processes exit, with a 300-second preparation limit and five seconds per control request; control failure is an infrastructure error. These scheduling details do not change the candidate's published 1,800-second preparation and ten-second request limits.

The 64 GiB storage allowance is audited rather than enforced by a Docker filesystem quota. Storage inspection runs during work and after commands; device/inode identity avoids counting hard links or repeated references twice. Inspection failures fail closed. Supervisor capabilities and host requirements are described in the validation section above; submitted commands remain unprivileged.

### Repeated verifier measurements

Each candidate/control preparation runs once. Each query runs in five independently shuffled passes; latency uses the median of its five times, then averages queries within each group and gives groups equal weight. All five quality passes must satisfy the existing gates, and failed or missing requests remain in the quality denominators. GPU memory remains the sampled peak across preparation and queries. The 9,900-second primary budget covers candidate preparation/requests (1,800 + 5,000 seconds), control preparation/requests (300 + 2,500 seconds) and 300 seconds of overhead. The 11,400-second verifier envelope also covers the unchanged 1,200-second integrity audit and finalization. Earlier three-pass timing records do not establish calibration for this five-pass protocol.

## References

[assets.json](assets.json) records the immutable input sources and hashes; [assets/model/probe.json](assets/model/probe.json) records the probe representation and provenance.
