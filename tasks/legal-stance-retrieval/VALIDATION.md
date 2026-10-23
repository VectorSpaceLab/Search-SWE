# Local validation — 2026-10-15

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

The local task package, assets and deterministic verifier were exercised.
This record does **not** claim a completed coding-agent evaluation, a successful
live integrity-judge call, or remote asset publication.

## Final contract and revisions

Current task version: `0.1.2`; the full runtime checks below were performed on
`0.1.0`. The verifier and hidden data are byte-identical in this revision.
Parent checkout inspected:
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8`.

Current instruction SHA-256:
`a41d40275ff625384a8b8a6d3ec422f605ace66693dd8424bc5c41bbfba7a056`.

The prior instruction fingerprint was
`c3d91f43b22204720b85e67058bcbd474608c601765f72ae0a0ae60b0f2d97d5`;
its source and validation record are archived in the author workspace.

Author-side evidence is under
`task_development/legal-precedent-retrieval/package-build/validation` in the
parent workspace. `revision.json` fingerprints the final task code, instructions,
configuration, hidden inputs and manifest. `input-inventory.json` in its parent
fingerprints the packaged public and private data. Test queries/qrels are copied
byte-for-byte from the user-approved cleaned export.

Reviewed precedents, structural reuse and the source/request equivalence check
are recorded in README.md and instruction-audit.md. Fenced command examples
intentionally follow the user's established preference over the generic skill
rewrite convention. No arbitrary result size or regular-file restriction was
introduced. No changes were made to other tasks; four shared inventory/document
entries were extended to register this new GPU/API/audited task while preserving
pre-existing worktree changes.

## Checks performed

| Layer | Command / evidence | Result |
| --- | --- | --- |
| Task grader and judge-transport tests | `python -m unittest discover -s tasks/legal-stance-retrieval/tests -p 'test_*.py'` | 23 tests passed |
| Shared hardware/network/judge integration | `python -m unittest scripts.tests.test_task_images scripts.tests.test_network_policies scripts.tests.test_rewardkit_deepseek` | 21 tests, 19 passed, 2 skipped because optional installed-package integration dependencies are absent |
| Runtime assets | `python scripts/download_assets.py --task legal-stance-retrieval --verify-only` | All 13 current files verified, 1.14 GiB; two unused metadata files removed in v0.1.1 |
| Local staged release check | Repository `check_release(..., hf_data=..., verify_data=True, allow_unpublished=True, packages=[task])` | Zero errors; one expected unpublished-data warning |
| Normal review-stage checker | `python scripts/check_tasks.py tasks/legal-stance-retrieval` | Only the three unpublished dataset revisions are rejected; no fabricated remote pins |
| Both Compose overlays | `docker compose ... config -q` with temporary base service | Passed |
| Shell and Python syntax | `bash -n tests/test.sh`, `python -m py_compile ...` | Passed |
| Diff whitespace | `git diff --check` | Passed |
| Harbor launch preview | `bash scripts/run_task.sh --task legal-stance-retrieval --openrouter --dry-run` | Passed; no model was invoked |
| Agent and verifier images | `docker build` of both task contexts | Both built successfully from the shared GPU image |
| Agent-visible mounts | Networkless agent-image container | Corpus/training/model/docs visible; no hidden tests or starter |
| Public/private split and evidence references | Author-side JSONL validation | 5,318 propositions, 10,636 public rows, 311 private rows; exact query text and IDs disjoint; all evidence IDs exist |
| Frozen baseline arithmetic | Saved reference rankings rescored through this grader | Exactly `0.5610484855098774` |

The default native-provider launcher preview required `AGENT_OPENAI_BASE_URL`;
the configured OpenRouter preview succeeded. No shared `.env` was edited and no
credential value was printed or copied into the package.

The repository-wide unittest discovery was also attempted. After 20 completed
test markers and an HF proxy TLS fallback notice, it remained inactive without
identifying the current test. Only that author-launched process was stopped.
Its log and status are retained; it is **not** reported as a full-suite pass.
Task-local tests and the targeted shared integration suite completed separately.

## Real local embedding retrieval

A genuine untrained 0.6B implementation built its own document embeddings from
the complete corpus, encoded unseen inputs, performed exact cosine Top-10
ranking and wrote the specified JSONL. It received no labels or saved rankings.
Its author-only source is `package-build/baseline-submission`, outside both task
images. The build and query commands were launched by the actual verifier as
UID 10001 inside a separate container, with network disabled and no API keys.

Hardware: physical **GPU 2**, NVIDIA A100-SXM4-40GB; 16 CPU quota, 32 GiB memory,
1 GiB shared memory; BF16, SDPA, document batch 24 and query batch 32. Only that
GPU was requested by UUID. GPU 3 and other users' processes were untouched.

| Measurement | Observed |
| --- | ---: |
| Fresh document build invocation | 62.0663 s |
| Whole 311-query invocation, including Python/model startup and output writing | **10.4288 s** |
| Mean NDCG@10 | **0.5574347355269109** |
| Frozen reward baseline B | **0.5610484855098774** |
| Normalized retrieval reward | **0** |
| Execution/output validity | true |

This validates the 20-second execution contract on the tested A100. It is one
full invocation, not a percentile or cross-hardware latency guarantee. The
historical 9.002 seconds was a sum of warm serial query timings; it was not
used as a fresh end-to-end measurement. Batch grouping and runtime differ from
the historical reference. The observed score variation is recorded rather than
silently recalibrating the user-approved anchor. Earlier saved batch32 predictions
score 0.5627418532111463 on the same test; the exact serial reference still
reproduces B with the final grader. No qrels or examples were changed for this run.

The first author baseline attempt failed because its JSONL reader used Python
`splitlines()`, which also splits Unicode separators inside legal text. The
baseline reader was corrected to iterate physical lines; the second attempt
above completed. The task grader already iterated physical lines, and neither
the corpus nor the task contract needed modification. No fine-tuning or positive
training-improvement claim is made by this baseline run.

## Container failure and isolation checks

The actual `tests/test.sh` was run in disposable, networkless containers with
five author-only fixtures. These are grading fixtures, **not genuine retrieval
solutions**, and are never mounted into the task environment or published as
agent examples.

| Fixture | Deterministic outcome |
| --- | --- |
| Complete ideal Top-10 rankings | Valid, NDCG@10 1, normalized retrieval reward 1 |
| Duplicate document IDs | Invalid, zero |
| No output file | Invalid, zero |
| Complete output followed by sleep beyond deadline | Invalid at 20 seconds, zero; process group terminated |
| Attempts to read hidden qrels/grader/trajectory or write reward/trajectory/app | Access denied; subsequent valid fixture output still scored correctly |

The boundary fixture also checked that hidden query text did not exist before
build completion and that judge credential variables were absent in submission
processes. Baseline and fixtures confirmed `/app` is not writable by the
submission UID while the index and result paths work.

All these local runs deliberately supplied **no live judge credentials**. The
full supervisor therefore returned nonzero and final reward zero even for a
perfect grading fixture. This is the expected fail-closed audit behavior, not
a completed trajectory audit. `evaluation.json` records deterministic retrieval
quality; `reward.json` records the separate final gate. No fallback judge pass
was inserted. Unit tests exercised passing and failing judge decisions without
making a network request.

## Remaining evaluation and publication

- A configured coding-model Harbor trial and live trajectory audit have **not**
  run. The applicable create-searchswe-task skill requires an actual configured
  coding-model run as a validation layer. The user's stop on paid author-side
  API use remains in effect; no model or judge call was made to satisfy this
  layer. There is no evaluated agent model, reasoning effort or genuine coding
  trajectory to report. The container fixture's empty trajectory is explicitly
  not a model trajectory.
- No assets were uploaded, no model weights trained, and no commit/PR was made.
  The local dataset staging is complete, but its immutable remote revision must
  be supplied after separately authorized publication before claiming remote
  reproducibility or merge-ready release status. Local restores are complete.
- No arbitrary new quality threshold was added and no test was removed in
  response to the baseline score. Final model-level solvability/improvement
  should be assessed in the later authorized coding-agent run.

## v0.1.1 focused verification

The instruction was shortened at the user's request. Annotation commentary, training-label warnings, development/batching advice and the numerical reward anchor/formula were removed from the agent-facing prompt; their author-side records and scoring implementation remain intact. Raw instruction and the correspondence audit were updated.

The two `model-metadata` files, their restored model-directory copies and their asset entries were removed, and `package_task.py` now skips them. All 13 remaining assets passed SHA-256 verification. A networkless CPU container successfully loaded both `AutoTokenizer` and `AutoModel` with `local_files_only=True` after their removal (`model_type=qwen3`). This check used no GPU or API.

Every file under `tests/`, including the scorer, frozen qrels and normalization record, matched the previous revision's SHA-256. Local unpublished-release validation and diff whitespace checks passed. The prior full baseline run was not repeated for this documentation/optional-file change. No coding-model evaluation of the revised instruction is claimed.

The agent development/training budget was corrected to **6 hours (21,600 seconds)** at the user's request. The request, structured source, author overview, correspondence audit and `[agent].timeout_sec` agree. Build and query deadlines are unchanged. No coding-model trial was run for this correction.

## v0.1.2 examples interface

The public data directory and container mount are `/task/data/examples`. Both public JSONL files use the `example_` query ID prefix; the original source IDs are mapped bijectively. All 10,636 example queries and labels were compared against their original source records, confirming unchanged claim text, stance and relevant document IDs. The directory rename, regenerated asset manifest, local staging and packaging script agree. The original source/audit files were preserved.

Agent-visible instructions and resource docs were checked for method hints and source-split naming. The model is presented only as an available resource. Public API/model boundaries still apply; the hidden audit continues to permit legitimate use of the supplied model without requiring a particular method. The query/label mapping and absence of the old directory were confirmed in a networkless CPU container. Local staged release checks passed with the existing unpublished-assets warning. No GPU or API was used.

The verifier and frozen hidden inputs were fingerprint-compared against the previous revision and are unchanged. No new full model run is claimed for this path/prompt revision.
