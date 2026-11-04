# Validation evidence

## Agent-facing cleanup — 2026-11-04, v1.0.0

The task instruction and two resource documents now omit test-overlap statistics, biological generalization claims, archive-transfer internals, judge-service failure handling and report-field inventories. The two resource documents use one source line per prose paragraph. The public evaluator CLI accepts only public-validation options; `tests/grade.py` still calls `evaluate(..., full_queries=True)` directly. Draft/author-only annotations were removed from the shared ranker and worker. Scoring, encoder execution, artifact collection, inputs and resource limits are unchanged.

The public runtime remains necessary for validation, encoding adapters and submission transfer. The author-side data preparation tool has been moved outside the task package; normal setup continues to use the prepared assets. Original archive hashes and test provenance are retained in [SOURCES.md](SOURCES.md), and the complete internal protocol remains in [raw-instruction.md](raw-instruction.md).

The two environment documents were subsequently shortened using `code-embedding-finetuning/environment/docs` as a style reference. They retain the interpreter, input/work paths, public-tool entrypoint and resource-access policy. Detectable package/hardware details and repeated encoder, scoring, timing and submission rules were removed; those requirements remain in `instruction.md`. This follow-up changes documentation only and preserves one source line per paragraph.

## Disk workspace correction — 2026-11-04, v1.0.0

Both Compose overlays now leave `/app` and `/tmp` on the container's writable disk layer instead of mounting 95 GiB and 1 GiB tmpfs filesystems. This removes unnecessary competition between stored checkpoints/caches and the 16 GiB memory allowance. The 64 MiB `/dev/shm` remains available for IPC. Numerical resource budgets, scoring and the submission contract are unchanged; version remains 1.0.0.

The collection hook remains responsible for stopping background work, checking the 256 KiB submission limit, and producing a validated snapshot for the separate verifier. Packing and restoration work on disk and do not require tmpfs. Its implementation is unchanged apart from the introductory comment.

The 100 GiB limit remains a task budget, sampled by `Resources.check()` during public/final evaluation. Harbor 0.22.0's Docker backend does not enforce a development disk quota from `storage_mb`, and this task does not use the repository's optional bounded-filesystem preparation. Removing tmpfs does not create a hard disk quota; provisioning adequate host disk and honoring the development budget remain necessary. Disk page cache can still count toward cgroup memory, but persisted files no longer have to remain in tmpfs.

Both actual Compose overlays rendered successfully with a temporary base service. A CPU-only smoke test used the cached phase images, current runtime, configured memory/PID/shared-memory limits, and no GPU or input/model mounts. Both `/app` and `/tmp` reported `overlayfs`; `/tmp` retained mode 1777. The real collection hook completed, files remained readable after the agent container stopped, and restoration in a separate container preserved both fixture SHA-256 hashes and removed the staging archive. Seven existing kernel-boundary tests passed on disk, including hidden-file protection, privilege/network restrictions, writable scratch, CPU DataLoader workers and IPC cleanup. The 28 existing CPU tests and task static validation also passed.

These checks did not rebuild images or run a full GPU/model trial. Reproducible smoke code, rendered Compose configurations, image IDs, file hashes and boundary-test output are retained in the external review directory `reports/2026-11-03/storage-audit-evidence/`.

## Runtime review fixes — 2026-11-04, v1.0.0

Phase cleanup now verifies that submission processes have exited, removes their System V shared-memory segments, message queues and semaphores as the owning UID, and checks that no such objects remain. Existing POSIX shared-memory cleanup remains in place. Supervisor-owned IPC objects are preserved; no additional container capabilities or mounts were added.

Submission freezing preserves executable files as mode 0555 and other regular files as 0444. The archive/restore/freeze regression executes a supplied helper under the actual unprivileged boundary, while retaining the 256 KiB size and read-only submission requirements.

Storage sampling now tolerates disappearing temporary files and counts relevant open file descriptors, including unlinked files and memfd objects. Named hard links retain per-path accounting; descriptors do not duplicate files already counted. The supervisor inspects worker descriptors with matching filesystem IDs while retaining its root real/effective/saved identity. Workers restore normal nonroot procfs visibility after dropping privileges. A live process that prevents inspection fails the resource check; ordinary process exit is handled separately. This remains sampled accounting, not a development filesystem quota.

The two stale README/raw-instruction descriptions of the resource guide were corrected. Task version, initial-release changelog entry, numerical budgets, encoder interface and scoring are unchanged.

All 44 CPU/container tests passed: 28 metric/ranking/transfer/finalizer tests, eight kernel-boundary tests and eight runtime regressions. Cases include all three System V IPC families, preservation of supervisor IPC, temporary-file races, sparse files exceeding the total limit before and after unlink, an unprivileged child holding deleted files, duplicate descriptors, a process hiding its descriptors, normal child exit, executable artifact transfer, hidden-file protection and CPU DataLoader workers. The IPC case was rerun after strengthening the supervisor-object assertion. Task static validation reported zero errors and `git diff --check` passed.

The tests used the cached verifier image with the current runtime and tests mounted read-only in a disposable container, with no network or GPU and with the task's CPU/memory/PID/shared-memory limits. Only NVML reads were stubbed for storage-only checks. From the mounted tests directory, the test command was:

```bash
PYTHONPATH=/task/runtime /opt/conda/bin/python -m unittest test_metrics test_ranker test_transfer test_finalizer test_boundary test_runtime_cpu -v
```

Logs and final file hashes are retained in `reports/2026-11-03/35-fix-evidence-20261104/` outside the package. No image rebuild or complete GPU/model trial was run; the historical trial limitations below still apply.

## Parameter basis and limits of the evidence

| Parameter | Basis |
| --- | --- |
| Reciprocal Top-1, equal dataset weights | Task-defined paired-recovery objective; reward is the direct success fraction, with no fitted quality anchors. |
| 64-dimensional vectors | Deployment interface; 10,000 float32 vectors occupy 2,560,000 bytes before IDs/metadata. |
| 256 KiB submission | Deployment size cap; the historical v0.6.0 trial below submitted 255,560 bytes. |
| 900-second preparation, p95 ≤ 1 second, 3-second query deadline | Execution limits; the historical trial passed them. These values are not claimed to be statistically derived optima. |
| 3,600-second development | The historical trial used 2,844.161508 seconds. An author reproduction budget separately totals 3,463.961612 seconds from measured components; that was not a fresh complete cold run. |
| 16 GiB container memory | Current resource limit. The available historical trial used a 64 GiB container limit and does not establish a successful solve under the current limit. |

Historical evidence was found in the author-local directory `contributing/dev/protein-text-bidirectional-retrieval/fixed-vector-interface-proposal/`, outside this task package. It is retained as historical evidence, not exposed to the solving agent:

| Record | SHA-256 |
| --- | --- |
| `formal-evaluation-summary-r1.json` | `e4238e15449bc5f3da53821b99ed3e536519901a491ceea371dfeaa4307cd8fc` |
| `formal-v060-source-freeze.json` | `2e6d3c860247d3b379f1f2d2369dcf2cd800ff2bd3b8bf88842bbf9c42683b6f` |
| `reference-production-budget-final.json` | `060ab097eb8a4ec178dd242122d5056eddd595cebc1792cfca5036e2163c5e65` |

The recorded 2026-10-20 v0.6.0 Codex/OpenRouter Luna/max trial completed 40,000 valid requests with no timeouts, paired-success quality 0.1979, score 19.79 and an accepting healthy integrity judge. Maximum group p95 was 0.0305053 seconds and maximum preparation time was 57.2001 seconds. Its container memory limit was 64 GiB; the verifier recorded a peak of 2,790,043,648 bytes. A low observed peak does not substitute for testing with a lower enforced limit. Before this cleanup, the current worker, ranker, metrics, isolation and transfer hashes matched the historical freeze; evaluator and task documents were different.

No new coding-agent or GPU trial was run for this cleanup. Current-prompt performance and complete development/verification under the current 16 GiB limit remain unverified; a new trial must retain its task revision, resource measurements, trajectory and judge health. Historical scores must not be relabeled as results for the current revision.

## Mounted model documents

On 2026-11-04, the three Markdown assets were fetched at the immutable revisions in `assets.json`; their byte lengths and SHA-256 hashes matched the manifest. The ESM-2 README is a general model card, and BiomedBERT supplies a general model card and MIT notice. No task-specific labels, trained alignment solution or author experiment results were found. Keep these upstream documents unchanged; links to other models do not expand this task's resource permissions.

## Checks

The 28 existing CPU tests for metrics, ranking, submission transfer and finalization passed using Python 3.13.13. CLI dispatch checks verify public evaluation, rejection of `--full` and the separate verifier's full-evaluation call without running GPU workloads. Task static validation and `git diff --check` cover package syntax and whitespace. These checks do not establish GPU runtime or model performance.
