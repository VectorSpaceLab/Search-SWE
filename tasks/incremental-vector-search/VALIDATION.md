# Incremental Vector Search validation — 2026-11-05

## Scope

The task remains a CPU-only incremental vector search benchmark: two fixed collections, ten insertion stages, five retrieval sizes, a 10% exact-search time gate, and logarithmic missed-neighbor reduction over the public PQ reference. The collection bytes, JSONL submission interface, single-CPU query rule, 16-CPU build/insertion allowance, 32 GiB RAM/storage, 120-minute agent budget and author jianlyu are unchanged. The source checkout was based on `783d2eeafd580f64c404da94dfc05733811d5c0f`. Other tasks' changes are outside this work.

Read-only structural references were `tasks/biomedical-graph-retrieval` for validation/hidden-data separation, the shared CPU image/docs, and the supplied agent-docs/storage audits. Agent-visible Markdown is unwrapped. Environment/resource docs describe the CPU-only local-vector setting. No unnecessary workspace tmpfs was added. The instruction keeps the task contract; calibration, cache and repeated-judge implementation details remain outside the agent-facing request.

## Completed implementation

- CPU IDs are selected from the current legal allocation. Runtime-dependent exact targets are regenerated when needed, rather than rejecting every Faiss binary different from the author's original runtime.
- The verifier performs five independent complete incremental replays per collection. Build, insertion and stage/K query gates use their five-sample medians. Each cell's quality comes from its median-time replay; missing timing samples count as infinity. Invalid execution/resource violations still fail the collection. The trajectory compliance audit remains single-run and uses `jailbreak_judge` consistently.
- The normal launcher invokes `tools/prepare_task.py` before Harbor and before the coding-agent time limit starts. Preparation errors prevent agent launch. Configuration checks and dry-run previews do not execute the helper. The shared integration is an optional package hook; no other current task supplies it.
- Preparation verifies all input bytes and repairs public input/reference read permissions before mounting them read-only. The review reproduced UID 10001 failing to read the original mode-600 references; real container reads pass after repair. Hidden test file permissions are not broadened.
- Platform caches are selected by hardware, CPU allocation, numerical runtime, data hashes and calibration/grading/reference code. Boot ID is excluded. Publishing unchanged files at a new HF revision does not invalidate the cache. Completed output hashes are checked before reuse. Corrupt/partial output cannot be reused; cache creation is locked and atomic, and both phases retain the same immutable cache path.
- Initial calibration is bounded by 24 hours; container builds by 1,800 seconds and key probes by 120 seconds. Interrupted or timed-out preparation removes its own disposable container. Preparation measures each exact/PQ reference once per collection; formal submission evaluation still measures five replays and uses timing medians. Cached launches skip reference measurement. This automation does not remove the first calibration's computational cost.
- `assets.json` now covers all 28 finished inputs: 18 public files under `data/` and 10 held-out files under `tests/data/`. The standard downloader and offline publication helper accept `tests/data/`. The duplicate hidden manifest and manual preparation entrypoint are removed. No separate hidden archive, source shards or generation script is needed to restore the task. Only public mounts reach the agent.

The shared changes are limited to the optional pre-agent hook, downloaded verifier-file paths, matching offline publication support/docs, and regressions. The task remains the only package using this preparation hook.

## Checks executed

| Check | Result |
| --- | --- |
| Download, disk planning, preparation hook, task workflow, release and launcher regression suites | 85 tests passed |
| Actual launcher with a fixture preparation hook and mock Harbor | Preparation occurs before Harbor; returned settings reach it; failed preparation blocks it; dry-run/check do not execute preparation |
| Disposable offline verifier container, 16 CPUs / 32 GiB / 256 PIDs, actual subprocess isolation | 36 tests passed on the single-reference preparation revision |
| One exact and one partial-reference preparation replay, plus five formal deadline-failure replays | Passed; preparation makes exactly two evaluator calls per collection, reference time gates remain enforced, formal timeout aggregation retains five samples |
| Cache reuse, changed allocation, corrupted output, failed preparation and changed input | Passed |
| Reboot and publication-only metadata changes | Do not invalidate an otherwise identical platform/data cache |
| Portable offline publication helper | 13 tests passed, including held-out files under `tests/data/`; no remote calls |
| Agent and verifier Dockerfile builds | Passed; automatic helper rebuilds the current verifier image before measuring |
| Actual cache-key probe with the 28 current inputs | Passed in the real preparation image |
| Current full-data verifier preflight with the reused first-reference results | Passed; accepted `reference_repeats = 1` and formal `timing_repeats = 5` |
| Actual UID 10001 reads of both reference programs and both corpus dimensions through read-only mounts | Passed |
| Fresh empty-directory restore using the standard downloader with `--kind data --local-files-only` | All 28 public/hidden files restored, zero failures, 2,789,338,762 bytes |
| Task-scoped release check against local HF staging with `verify_data=True, allow_unpublished=True` | Zero errors; one expected publication/pin warning |
| Source/shell syntax and `git diff --check` | Passed |

The small synthetic timing fixture gives its exact reference a deterministic extra query cost so the partial reference does not race the serialization/scheduler overhead of two tiny queries. This changes only the regression fixture, not production reference code or timing limits.

## Full-scale validation and single-reference correction

The original background job `jobs/task-preparation/incremental-vector-search-20261104T174816Z/` completed successfully at 2026-11-05 02:53:24 UTC. That historical run measured each exact/PQ reference five times; the user subsequently required preparation to measure each reference only once. The current preparation code makes one complete evaluation call per reference and collection. Formal submitted implementations still run five times and use median timing gates.

The completed job saved every replay. The current platform cache was constructed from replay zero of each reference, without rerunning full-data searches or selecting the best result. Reuse checked the prior cache hashes, unchanged measured controller/reference code, machine allocation, numerical runtime and input hashes. The new single-reference preparation code validated those complete measurements and generated the current limits. The old cache and logs are retained unchanged. Source records, conversion code/logs and the successful automatic cache-hit check are under `jobs/task-preparation/incremental-vector-single-20261105T033320Z/`.

The first exact replays recovered every requested neighbor. Their query durations totaled 2,023.775496 seconds for 1536 dimensions and 4,024.130810 seconds for 3072 dimensions, approximately 1.7 hours combined. The first PQ-reference query durations totaled 260.310230 seconds across both collections; build/insertion and target setup add overhead. Baseline missed-neighbor counts are 6,951,210 and 951,853 respectively. These are observed reference measurements, not coding-model scores. The active cache declares `reference_repeats = 1` and `timing_repeats = 5`.

A normal preparation call reused the new cache instead of launching reference searches. No fresh coding-model trial or live compliance-audit call has been run for this revision. Reference calibration establishes current-platform budgets and anchors; model difficulty and final model scores still require a model trial.

## Publication and restoration

The active offline staging is `../task_development/incremental-vector-search/delivery/hf-data/`, relative to the repository root. It contains all 28 finished files and a task-only manifest. `delivery/automatic-restore/` was populated from an empty directory through the normal downloader, including `tests/data/`. Earlier hidden tar archives are historical and no longer required by any runtime path.

The final batch publication is complete: [HF publication PR #12](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/12) merged as official revision `13c218a82ae222dc65a4eeb070e4f46602b5cadb`. All 28 entries in `assets.json` are pinned to this immutable revision. The publication adds 2,789,338,762 bytes of finished public/verifier inputs and preserves all 52,413 previously published manifest entries. Source cards and derivation notices accompany the data; machine-specific caches and task code are excluded.

The standard downloader restored all 28 files from the published revision into an empty output directory using fresh HF and Xet caches, with zero failures and size/SHA-256 verification. A separate parallel prefetch populated the same fresh HF cache for 26 files and independently checked their hashes. The final repository release check reports zero errors and zero warnings, and the incremental task's merge-ready check reports zero errors. The whole-repository merge-ready preflight had no errors apart from these 28 then-unpublished pins; publication resolves those entries without changing their paths, sizes or hashes.

Publication integration checks ran 351 repository unit tests (349 passed, two optional checks skipped), 13 maintainer-skill tests and 10 authoring-skill tests. Credential fixtures were updated to match the already-configurable ICSI/long-PDF answer judges; task behavior was not changed for publication. The publication checkout includes upstream main `67a56620abf5c13b4ab12bea57f2f62ee274b002`. All 16 reviewed instructions retain their pre-publication hashes. No new coding-model, GPU benchmark or live judge trial was run.

## Final source hashes

- `instruction.md`: `6d30f17afdd55ebd36adbb8b4dafd7a4a533a54b5d36de4fa0fb2112ce4fd303`
- `assets.json`: `db06c067275cdff184700367a24b589df0a7deccc38aedd5ff0d02b1578ae835`
- `tools/prepare_task.py`: `9a265e39ebfa605ac7e6b8fe3f937a2a1c49de74ca6754a6da79d26f57fc9e0b`
- `tests/calibrate_platform.py`: `50c6cb4ae071fdaa205c3b967ea50bd802d91f21fe6187e3bedcffe6e6f36714`
- `tests/grader.py`: `3946df617d407d3740a035124606eeb67f540930154332c23216fc9f9009c135`
- `tests/metrics.py`: `29408018e354177c42c027734dd67fd54b6a707dec37585049ea4118ff55aa8e`
