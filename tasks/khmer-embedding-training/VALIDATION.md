# Validation — 2026-11-05

This record covers the current package corrections. No fresh coding-agent trial, full-corpus GPU evaluation or live compliance-judge request was executed. The historical baseline numbers are retained, not remeasured.

## Scope and reference

The task objective, backbone and optional development model, three public examples, 1,000 hidden questions, answer matching, candidate deadlines and final score curve are unchanged. The changes correct nested time budgets, validate the audit gate, align the primary score report with finalization, standardize public data paths and remove GPU model/VRAM specifications from task-authored resource descriptions. There is no tmpfs configuration to remove. Agent-facing prose paragraphs are not hard-wrapped.

The checkout reference is `783d2eeafd580f64c404da94dfc05733811d5c0f`. Resource documentation follows `docker/gpu/environment.md`; validation layout follows `tasks/biomedical-graph-retrieval`. The final-gate checks follow the single-compliance-audit pattern used by the current neighboring join-aware and instruction-following tasks, retaining this task's own criterion name, rubric and backend. Other tasks were not modified for this work. The pre-edit `raw-instruction.md` SHA-256 was `8738ed809e517f467b5a5163133430d60602d014b22a9937fd68b126808652f8`.

## Timing and randomness

| Stage | Limit |
| --- | ---: |
| Agent development | 21,600 s |
| Checkpoint load | 300 s |
| Index construction | 43,200 s |
| Retrieval | Two calls of 1,800 s each |
| Primary evaluator | 48,000 s |
| Single compliance audit | 900 s session inside a 1,200 s wrapper |
| Finalization | 30 s |
| Outer verifier | 51,000 s |

The candidate stages total 47,100 seconds. The primary wrapper leaves 900 seconds for scoring and cleanup. The outer wrapper leaves 1,735 seconds beyond the primary, audit and finalizer budgets and their 35 seconds of termination grace for preparation, audit snapshotting and cleanup. Previously the primary wrapper was shorter than the combined candidate allowances. Candidate training, build and retrieval limits were not reduced to fix this.

Quality is deterministic Recall@100 from answer-token matching. Execution time is diagnostic and constrained by deadlines; it is not a score term. There is no answer/evidence LLM judge to repeat three times and no scored latency metric to repeat five times. The existing independent compliance audit remains one call.

## Audit and scoring

A healthy audit needs an exact binary aggregate, one matching `jailbreak_judge` criterion, a nonempty judge response and no reported judge error. The primary and audit processes must succeed and the trajectory must be a nonempty regular file. A confirmed rejection is a valid zero. Missing, fractional, inconsistent or failed audit output is an infrastructure failure, with a zero reward artifact and a nonzero verifier exit. Stale output is removed before execution, and cleanup includes the retrieval role.

Both `grader.py` and `finalize_reward.py` now call `normalize_score`. The existing piecewise curve is unchanged: raw Recall@100 0, 0.595 and 1 map to rewards 0, 0.15 and 1. The previous primary report used a different improvement formula while the finalizer used the piecewise curve. The stored untrained-backbone Recall@100 0.279 remains diagnostic.

The reference encoder's only changes are its public query default and the matching public answer-file default. Encoding and answer-matching algorithms are unchanged, as are all hidden data and baseline metric values. Its recorded fingerprint changes from `47476fb4bee549994e8bf0acca5089c3a69ae0c8541943c734a93c33b3e39e30` to `e475e55238e72d1e176539acb5c6dc3a1c896d25809771839c2e06e275740db1`. This is a reviewed path migration, not a new baseline measurement. Formal grading still executes the submitted `build.sh` and `run.sh`, not this reference encoder.

## Public assets

[HF PR #11](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/11) was reviewed and merged as official dataset commit `8431ce24f7706eb51ff68aef7494f2b2780319a1`. The existing 52,411 manifest entries were preserved; two files were added, totaling 665 bytes. No hidden inputs, corpus or model weights were uploaded. Corpus and model upstream pins remain unchanged.

| Restored path | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/validation/queries.jsonl` | 393 | `7d0841a3218c9f20c99f89b2012770907802955d5021d649b9432a719cb7c4a9` |
| `data/validation/answers.jsonl` | 272 | `6887e0506b6a86d062e08dbf061dfad6fb82a88a88b1a960762f7837b31076fe` |

Fresh-cache downloads from the merged SHA match their recorded bytes and hashes. Joining the two files by their unchanged order/IDs exactly reproduces the original three public records. The original `asset-metadata/examples.jsonl` copy was removed after download verification. Provenance and Apache 2.0 source terms are recorded in the dataset metadata and [SOURCES.md](SOURCES.md).

## Local checks

- Built `search-swe-local:bingyu-khmer-verifier-20261105` successfully from the unchanged verifier Dockerfile. The agent Dockerfile is unchanged and was not rebuilt.
- Ran all task tests in a disposable verifier container with `--network none`, two CPUs, 4 GiB RAM, `PYTHONDONTWRITEBYTECODE=1` and `SEARCH_SWE_RUN_ISOLATION_TESTS=1`: **50 tests passed**. They cover tiny CPU checkpoint loading, offline execution and process isolation, strict audit validation, score normalization and supervisor budgets.
- Ran the budget test from the repository as well, where the outer `task.toml` is available: **one test passed**.
- Ran `python -B scripts/validation/check_tasks.py tasks/khmer-embedding-training --merge-ready`: **zero errors**. Python/TOML/JSON parsing, both Compose-overlay checks, shell syntax and scoped `git diff --check` passed. Public asset hashes, public/hidden ID separation, the shared GPU-document template and unwrapped agent-facing prose were checked locally.
- Ran the real `/tests/test.sh`, grader and finalizer in five disposable CPU containers with synthetic data and a stubbed audit backend: **five cases passed**, summarized below. Candidate processes used the actual separate build/retrieval roles; private-label access and network access were denied, and the built index was read-only during querying.

| Synthetic case | Verifier exit | Primary report reward | Final reward |
| --- | ---: | ---: | ---: |
| Healthy acceptance | 0 | 0.15 | 0.15 |
| Confirmed rejection | 0 | 0.15 | 0 |
| Fractional audit aggregate | 1 | 0.15 | 0 |
| Missing audit details | 1 | 0.15 | 0 |
| Failed build | 0 | 0 | 0 |

The accepted fixture uses a tiny locally created XLM-R model, five corpus rows and 1,000 synthetic questions, of which 595 match. It checks the unchanged score anchor through the actual execution path. Only the disposable fixture's baseline input hashes and audit backend are replaced; production baseline metrics, hidden data and audit code are not replaced. These are interface/isolation tests, not retrieval-quality results or live-judge validation.

Temporary author-only evidence is under `/tmp/bingyu-khmer-review-20261105-t2h0sj10/`: `unit-tests.log`, `integration_fixture.py`, the five JSON results and logs in `integration-evidence/`, and HF review/download records in `hf-pr.json`. These files are not public task inputs.

Full-corpus/model assets were not restored for this check. A fresh GPU trial remains necessary to measure current retrieval quality, end-to-end runtime and live audit health on the deployment platform. Removing a named GPU from the task specification does not establish CUDA/driver compatibility or performance on every GPU.

## Current file fingerprints

| File | SHA-256 |
| --- | --- |
| `instruction.md` | `3796a63e06f68c3aabd88b71584018e8b6ef92cc5128cb7faa876e08d907104e` |
| `raw-instruction.md` | `0ebafb0de4492c2cfe923411440577b5ca535fc458245ff59ce94d2fa6cd16de` |
| `task.toml` | `fe8f57b2ad250ab77c21f654049ff233b686f0f25542a7207048b0c6d95cbb89` |
| `assets.json` | `dc00b37ea4caee4db713a04e506f96b79f6efedf4033645a8a5298125ad553d7` |
| `tests/grader.py` | `96f57d8db560a947f00d52bb393c59f7dc249e6c0171f0b066eeef2b9d184f82` |
| `tests/finalize_reward.py` | `0986bb0c9b22aa8b7e15b1b53fae35fc92b04c4bb5ceebc6445e0d920c8854ad` |
| `tests/test.sh` | `180de0514600e876ce3e34fa4a86d3c60803ea4a4825a35a7e2323e92fa77625` |
