# Scoring revision — 2026-11-04

This record covers the requested score normalization change in the existing task, based on checkout commit `c7f8a8064e0ff1be30bca3bf4b42ab6b18e60b03`. No new task layout or external reference implementation was introduced.

## Contract

The zero-score baseline remains `B=0.9127469497437668`. The full-score reference is now `U=1`, giving normalized reward `clip((Q-B)/(1-B),0,1)` and displayed score `100 * reward`, subject to the existing integrity gate. The computation of Q, input assets, submission interface, GPU allocation, time limits and integrity checks are unchanged by this revision.

The formal grader reads `tests/scoring_parameters.py`; its existing linear reward function already accepts a reference of 1. The author-facing formula is recorded in `raw-instruction.md`, `task.toml` metadata and README. After the initial scoring change, the contributor shortened `instruction.md` and requested that it state the fixed hidden-set baseline and the objective to maximize quality without exposing the complete score formula. Environment documentation was also simplified. These prose changes do not alter the configured linear score.

## Offline checks

Python: `/data/Search-SWE-Workspace/Search-SWE/jianlv_workspace/envs/search_swe_cpu/bin/python` (3.12.13, NumPy 2.5.2).

| Check | Result |
| --- | --- |
| New `test_scoring.py` against the previous reference | Failed as expected: the real grader still used the old reference and saturated too early. |
| `python -B -m unittest -v test_scoring test_finalizer test_grader_import`, from this task's `tests/` | 11 tests passed after the reference change. |
| `python -B scripts/validation/check_tasks.py tasks/multilingual-vector-postprocessing`, from the repository root | 0 errors. |
| `git diff --check -- tasks/multilingual-vector-postprocessing` | Passed. |

The new tests call the actual grader with synthetic retrieval reports, use its real scoring parameters and reward function, and write reports only in temporary directories. They cover the unchanged zero-score baseline, linear intermediate scores, full credit at Q=1, invalid/nonfinite quality, and the final integrity gate. Retrieval execution and process cleanup are mocked; these tests perform no training, GPU work or API calls. The existing finalizer tests also exercise rejection, malformed/unavailable audit results and primary failure.

| Q | Expected score, matched within floating-point tolerance |
| --- | ---: |
| 0.9127469497437668 | 0 |
| 0.9353486724891793, the previous full-score point | 25.90364769946581 |
| 0.95 | 42.69541310800411 |
| 0.9563734748718834 | 50 |
| 1 | 100 |

## Revision and limits

- Initial scoring-change `instruction.md` SHA-256: `b0a6c3ff0f291deb2e43c1146b11f3dd04b0c79914955363a38f90f650f80558`.
- `raw-instruction.md` SHA-256: `6ccea6c911f43ee5500192b299f7c8e833e9f4275d75fedd673f04a5a91f9e50`.
- `tests/scoring_parameters.py` SHA-256: `731f5c287ebd9af7f3c8ded8279da5a82d24d3a6713cdc9b6ad1accea021682c`.
- `tests/test_scoring.py` SHA-256: `df7ea69c50187944dcc70655c26333fc50b210502f0082347e82622eae797d9f`.

No assets were downloaded or changed, no Docker images were rebuilt, and no full A100/model evaluation or live trajectory audit was run for this revision. These results validate score normalization and offline failure handling, not the difficulty or end-to-end performance of the revised task. Earlier model runs and their scores have not been rewritten; a fresh configured-model run remains outstanding for release validation of the revised instruction and scoring.

## PR preparation — 2026-11-04

Current instruction SHA-256: `1d377f808408765bea5758f7fe567b8f83de6106b382a72056e58e10c713d611`. The current task package passed the static checker with 0 errors. The offline scoring tests remain applicable to the unchanged scoring code; the final prompt has not yet been evaluated with a coding model.


# Runtime and resource revision — 2026-11-05

This revision implements the requested hardware, measurement, storage, integrity-result and resource-document fixes. Public development paths, assets and their Hugging Face pins remain unchanged by explicit request. The zero-score baseline, full-score point Q=1, nDCG aggregation, transform interface, six-hour development allowance, 16 CPUs, 16 GiB RAM and 100 GiB storage budget are unchanged.

## Implementation and contract review

- GPU checks require exactly one available CUDA device. They no longer require a particular model or physical memory capacity. GPU memory usage is diagnostic only. Instruction, task metadata, author contract and integrity rubric agree on one GPU.
- Evaluation performs five independent runs with fresh workers, transformed-document caches and temporary directories. Query order and consistency sampling use the same fixed seed in every run. Each query selects the median-duration sample, using the same sample's retrieval result; quality is not a selection criterion. Failed samples occupy the 0.5-second deadline, so at least three successful samples are needed. Equal durations prefer valid samples, then earlier rounds. An unavailable worker leaves later queries failed within that run. A consistency-probe timeout also affects only that run; a demonstrated inconsistency, preparation failure or resource violation still invalidates the whole task.
- Removed general workspace and transport tmpfs mounts in both Compose files. Workspaces use the container's disk filesystem; inputs, runtime and agent documents/baselines retain read-only bind mounts. Submission collection, hashing, restoration, unprivileged evaluation and read-only submitted files remain in place. The 1 GiB IPC shared-memory area remains and counts against RAM.
- Added logical storage accounting over supplied input directories and writable task directories. The collector checks total usage after stopping agent work; the verifier samples usage and checks it before reporting. Framework transport/logs are excluded, and the rubric forbids repurposing them. This is logical-byte accounting, not an instantaneous disk filesystem quota.
- Integrity acceptance requires consistent aggregate, group score, criterion raw/value, no criterion/group error, a nonempty textual judge response, successful judge exit and a nonempty trajectory. Finalization propagates invalid primary measurements and unavailable/malformed audits as nonzero exits; healthy integrity rejection remains a valid zero. The compliance audit still runs once.
- Agent-facing prose remains unwrapped. The resource documents add the task-installed nvidia-ml-py package and remove the Harbor transport explanation. The instruction states the median query-latency limit without expanding internal round or audit machinery.

The read-only structural references were this repository's instruction-following-embedding runtime/Compose layout, memory-constrained-dense-retrieval audit finalizer, and the supplied workspace-storage audit report. Their task-specific scoring, data, model and resource limits were not copied. Source/request comparison covered the hardware count, disk versus shared-memory behavior, unchanged submission and data paths, median timing, retained preparation/resource failure rules and unchanged scoring objective.

## Verifier budget

| Component | Budget |
| --- | ---: |
| Preparation per measurement run | 1,800 s |
| Query deadline, per call | 0.5 s |
| Five runs of preparation, 13,002 queries and up to 103 consistency probes | 41,762.5 s |
| Primary supervisor, including trusted overhead | 43,500 s |
| Single integrity-audit wrapper | 1,200 s |
| Outer verifier, including setup, finalization and termination overhead | 45,600 s |

The outer limit is a worst-case allowance, not an observed runtime. Agent development remains 21,600 seconds.

## Checks performed

| Check | Observed result |
| --- | --- |
| Host: python -B -m unittest -v test_finalizer test_scoring test_grader_import test_measurements | 25 tests passed. Covers median selection, failed samples, preserved budgets, generic GPU initialization, storage accounting, score normalization and audit consistency/exit status. |
| Disposable offline verifier container: test_runtime_controls | 12 tests passed in 79.381 s, including known-good retrieval, fresh worker/workspace state, invalid output, timeouts, isolation, orphan cleanup, storage excess and artifact restoration. |
| Follow-up after handling consistency-probe timeouts | The new probe-timeout case and three affected existing controls passed in 36.216 s. Actual function inconsistency still fails; five timing rounds still complete after a probe timeout. This brings distinct container controls exercised to 13. |
| Two-container collect/restore smoke | A 33,554,537-byte, two-file submission transferred with identical hashes. /app, /tmp and /logs/agent were overlayfs in both containers. A sparse temporary file crossing the storage budget was rejected by the real collector. |
| Both Compose overlays | Successfully rendered; retained one GPU reservation, 16 GiB RAM/no swap and read-only input/runtime mounts; no workspace tmpfs or read-only root filesystem. |
| Static merge-ready check | 0 errors. |
| Python syntax, shell syntax and git diff whitespace | Passed. |
| Asset manifest and duplicate runtimes | assets.json unchanged; environment/runtime and tests/runtime copies agree. |

Evidence is under `/tmp/bingyu-multilingual-revision-20261105-ibtpn0lo/`: `container-controls.log`, `container-probe-controls.log`, `check_transfer.py`, `transfer-result.json` and rendered Compose JSON. The first transfer harness attempt failed on quoting in its synthetic Python fixture before collection; fixing that fixture produced the successful transfer result without a production-code change. An initial Compose assertion expected an integer where Compose JSON emits a byte-count string; the corrected check passed for both overlays.

The containers reused cached task images with the current runtime mounted read-only, CPU execution, no GPU allocation and network disabled. No full image rebuild, full-data GPU/model evaluation or live integrity API call was performed. These checks verify the revised runtime boundaries and scoring logic, not performance equivalence across GPU types or final task difficulty. A configured-model trial on the final revision remains outstanding for release validation.

Final instruction SHA-256: `79d2c9599be537d3fe345dc376290c1b66d59bb0d26e3bb904cbd291cdb79d25`. Final evaluator SHA-256: `c5f9cc040ee175a50699bff433bde3a1f848d204d649ebd33e4846f17f4f070a`. Final audit-finalizer SHA-256: `f2f4d7c174b78911ec9bd1b87fd7529be3127b235939dc9d70ef1400a3db2ed7`.
