# Local validation

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

## Baseline revision — 2026-10-23, v0.1.1

The user selected **0.310109** as the new zero-reward baseline. This is the
six-decimal rounding of untrained Stella without a query prompt on the final
4,851-document corpus and 122-query test set: **0.3101092896174863**. Source:
`../../../task_development/methodology-inspiration-retrieval/research/stella400m-v1/screened-v2-results.json`,
`models.stella_plain.recall3`.

The attainable Recall@3 ceiling remains **0.9901639344262295**. Quality Q maps
to `clip((Q-0.310109)/(0.9901639344262295-0.310109), 0, 1)`; a successful passing
integrity audit is still required for a positive final reward.

The saved Codex / `openai/gpt-6-luna` / `max` trial from 2026-10-22 has valid
results for all 122 queries, raw Recall@3 **0.32076502732240436**, and a
successful passing trajectory judge. Applying the new formula gives final
reward **0.0156693625514165**; its original reward under baseline 0.3388 was
zero. This is an offline recalculation using the saved evaluation and integrity
gate, not a new agent or judge run. The original run artifacts are preserved at
`../../../task_results/methodology-inspiration-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T093112Z/jobs/2026-10-22__17-31-54/methodology-inspiration-retrieva__PbJPQsK/verifier/`.
The evidence files are `methodology-inspiration-retrieval-eval/evaluation.json`,
`reward.json`, and `reward-details.json` (`final_gate`).

Validation for this revision: all 11 task-local unit tests passed; the TOML,
grader, scoring module and finalizer agree on the baseline; the production
scoring/finalizer functions reproduce the recalculated reward using the saved
integrity gate and the ceiling computed from the fixed labels. Both instruction
files are unchanged. The task static checker still reports the two existing
unpublished data revision errors for `data/corpus.jsonl` and `data/examples.jsonl`.

## Archived packaging validation — 2026-10-16, v0.1.0

Everything below records the original packaging checks with baseline 0.3388.
Statements about unperformed trials and scores describe that historical revision.

The local package, deterministic grader, isolated runtime and genuine Stella
baseline have been exercised. This record does not claim a completed coding
agent trial, live trajectory audit, training improvement or remote publication.

## Revision and contract

Task version: `0.1.0`. Parent checkout:
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8`.
`task_development/methodology-inspiration-retrieval/package-build/revision.json`
fingerprints the final instructions, configuration, verifier and hidden data.
`input-inventory.json` records source-row counts and fixed data checksums.
No commit or push was performed. Existing unrelated worktree changes were
preserved; four shared inventory/document files gained this task's entries.

The reviewed merged precedents, local verifier precedent and intentional
differences are documented in README.md and the author-side design record.
`package-build/instruction-audit.md` traces the structured and rewritten
instruction to the implementation. The user requested fenced build/run examples
and omission of the private reward anchor from solver-facing prose; both were
honored. No reference engine, answer table or authoring script is shipped.

## Completed checks

| Layer | Evidence | Result |
| --- | --- | --- |
| Deterministic contract | `python -m unittest discover -s tasks/methodology-inspiration-retrieval/tests -p 'test_*.py'` | 11 passed |
| Shared hardware/network/audit integration | `python -m unittest scripts.tests.test_task_images scripts.tests.test_network_policies scripts.tests.test_rewardkit_deepseek` | 21 tests, 19 passed, 2 optional dependency skips |
| Fixed inputs | `python scripts/download_assets.py --task methodology-inspiration-retrieval --verify-only` | All 17 files verified, 1.68 GiB |
| Local staged release | `check_release(..., hf_data=..., verify_data=True, allow_unpublished=True, packages=[task])` | No errors; expected unpublished-assets warning |
| Normal task checker | `python scripts/check_tasks.py tasks/methodology-inspiration-retrieval` | Only the two unpublished dataset revisions rejected |
| Compose overlays | `docker compose ... config -q` for both phases | Passed |
| Syntax/whitespace | `bash -n`, Python compilation, `git diff --check` | Passed |
| Launcher preview | `python scripts/run_task.py --task methodology-inspiration-retrieval --agent codex --openrouter --dry-run` | Passed; no model invoked |
| Docker images | Builds of both task contexts | Passed |
| Agent inputs | Networkless agent container with the declared mounts | Corpus/examples/model/docs visible, hidden tests absent |
| Model usability | Native SentenceTransformer load and backward pass in the actual agent image | Shape `[2, 1024]`; 270 finite gradient tensors, nonzero gradients |
| Reference arithmetic | Archived frozen rankings through this scorer | Mean Recall@3 `0.3387978142076503`, normalized reward 0 |

The local example export preserves all 11 source fields and duplicate rows.
Only the 3,106 test-source rows and 74 rows quoting test-source abstracts are
removed. The public corpus/test query hashes match the frozen screened-v2
exports. All 187 positives resolve to the corpus, and no test-source abstract
is present in the corpus or either abstract field of the public examples.

The first image builds were stopped during redundant npm downloads; moving
task-specific compatibility installation after the common cached layers fixed
this. The first author-side SentenceTransformer probe passed config options
as model constructor arguments and failed. Correcting the probe to use
`config_kwargs` succeeded; no model weights or benchmark data were changed.
The supplied model has unused original pooler weights; its documented mean
pooling and dense projection are used. This is not a newly initialized encoder.

## Genuine retrieval through the verifier

Author-only implementation:
`package-build/reference/{build.sh,run.sh,engine.py}`. It receives the raw
corpus and supplied model, constructs new embeddings in the verifier, and
serves unseen queries through a resident process. It never receives labels,
archived vectors or rankings. It uses FP32, official mean pooling and 1,024-D
projection, the official `s2p_query` prompt, native 512-token limit and exact
cosine ranking. Query batch size is 32.

The actual `tests/test.sh` and grader ran submitted code as UID 10001 in a
fresh verifier container: one physical GPU 0 (A100-SXM4-40GB), 16 CPU quota,
32 GiB RAM, 1 GiB shared memory, no network or API credentials. GPU use was
registered and released in the user's shared GPU record.

| Measurement | Result |
| --- | ---: |
| Build, indexing, model load and service readiness | 58.9424 s |
| Complete 122-query invocation | **1.3170 s** |
| Mean Recall@3 | **0.3387978142076503** |
| Frozen zero anchor | 0.3388 |
| Deterministic normalized reward | 0 |
| Execution and output validity | true |

The timed query invocation includes client startup, input reading, tokenization,
encoding, search, IPC and output writing. It excludes the preceding build and
resident-model initialization. This is a real whole-batch measurement, not an
estimate formed by multiplying a median. It confirms this baseline fits the
12-second budget on the tested A100; no API-latency guarantee is implied.

## Container failure and isolation checks

Six author-only grading fixtures used the same full supervisor and hidden
batch. The ideal answer table is a grader fixture, not a valid retrieval system
or solvability claim, and is never exposed to the coding agent.

| Fixture | Deterministic outcome |
| --- | --- |
| Complete ideal Top-3 lists | Recall@3 `0.9901639344262295`, reward 1 |
| Duplicate document IDs | Invalid, zero |
| Missing output | Invalid, zero |
| Query process exits 7 | Invalid, zero |
| Writes complete output, then exceeds deadline | Killed at 12.0001 s, invalid, zero |
| Hidden-data/log/reward/app boundary probes, then ideal fixture output | Access restrictions held, reward 1 |

Boundary checks include hidden queries being absent before build completion,
qrels/grader/trajectory unreadable to the submission, no write permission on
`/app` or verifier/trajectory logs, no examples in the verifier, and judge
credential variables absent from child processes. Background submission
processes were cleaned up before output scoring.

All these runs deliberately omitted live judge credentials. Therefore their
full supervisors exited nonzero and final rewards stayed zero, including the
ideal fixture. This is the intended fail-closed audit behavior. Deterministic
retrieval outcomes are in `evaluation.json`; final audit-gated outcomes are in
`reward.json`. Unit tests separately check passing, rejecting and missing audit
decisions. No paid API request or fake successful judge was used.

## Remaining layers

- No full coding-agent trial or live integrity judge was run. The repository
  authoring skill requires that additional layer for full validation. This
  delivery follows the user's package-only preference; no new paid trial was
  authorized or silently launched. There is no evaluated coding model,
  reasoning effort or coding trajectory to report.
- No fine-tuning experiment was performed. One backward pass proves runtime
  usability, not learning quality. The baseline validates execution and the
  anchor, not the size of the achievable improvement.
- The two public dataset assets are local and unpublished. They have exact
  hashes and local staging, but need an authorized upload and immutable remote
  revision before this package is merge-ready or remotely restorable.
- Shared integration and task-local tests passed; no full repository-wide
  test-suite result or live network policy/API call is claimed.
