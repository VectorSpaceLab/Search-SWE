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
