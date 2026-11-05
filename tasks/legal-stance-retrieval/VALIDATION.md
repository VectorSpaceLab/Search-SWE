# Focused verifier revision — 2026-11-05

Base commit: `783d2eeafd580f64c404da94dfc05733811d5c0f`. The user authorized three changes: consistent audit-result validation, five measurements of the 20-second batch deadline, and portable index-directory examples. The older sections below describe earlier revisions and do not validate the new five-round protocol.

## Scope and contract

The existing audit model, prompt, root execution and `isolated = false` configuration are unchanged. Resource documents, Dockerfiles, Compose mounts, API permissions, public examples, hidden inputs and the fixed baseline are unchanged. The index examples now use `/path/to/index`. Related timing descriptions and supervisor budgets were updated to match the implementation.

Run five complete build/query rounds in the same frozen query order. Because the interface allows services started by `build.sh`, each round uses a fresh build and index directory rather than reusing a service that has already seen the queries. Submission processes are stopped and writable work directories, POSIX shared memory/message queues and submission-owned System V IPC are cleared between rounds. Operating-system file caches are not flushed. Each build still has 3,600 seconds and each entire query batch still has 20 seconds.

Sort successful, valid batches by elapsed time; place failed, late or invalid batches after them, breaking ties by round order. Score the rankings from the third batch in this ordering, never the batch with the best relevance score. Fewer than three successful batches gives zero. Any build failure still gives zero. Binary NDCG@10 and `B = 0.5610484855098774` are unchanged.

The primary supervisor now allows 18,600 seconds: five times `(3600 + 20) = 18100` seconds plus 500 seconds for setup, cleanup and scoring. The outer verifier allows 20,100 seconds, covering the primary supervisor, existing 1,200-second audit, 60-second finalizer, 90 seconds of termination grace and 150 seconds of additional overhead. Agent time remains 21,600 seconds.

Audit validation checks the aggregate result, detail-group score, raw binary decision and normalized criterion value, together with nonempty judge output and absence of reported errors. Missing, malformed or inconsistent audit evidence writes zero and returns a nonzero status; a consistent rejection remains a valid zero. The shell preserves the finalizer's diagnostics on failure. The installed RewardKit detail schema was inspected when implementing these checks.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 LITELLM_LOCAL_MODEL_COST_MAP=true python -B -m unittest discover -s tasks/legal-stance-retrieval/tests -p 'test_*.py' -b`: **38 tests passed**. Coverage includes fresh round ordering, median-time response selection, two versus three failures, missing outputs, unchanged scoring/hidden hashes, nested budgets, and audit-result contradictions.
- `python -B scripts/validation/check_tasks.py tasks/legal-stance-retrieval --merge-ready`: **0 errors**. Python/TOML parsing, shell syntax and scoped `git diff --check` passed.
- Seven offline fixtures exercised the actual `test.sh`, grader, process cleanup, transport wrapper and finalizer in disposable containers with private PID/IPC, no network, 2 CPUs and 4 GiB RAM. Every fixture built five times and audited once. Build-started background services worked, prior query files/index state were absent before the next build, and POSIX/System V shared memory from a preceding query was cleared.
- The timeout fixtures used the real **20-second** cutoff; timed-out calls measured approximately 20.20 seconds including termination cleanup. No reduced deadline or fake elapsed time was used.
- After tightening the detail-group score and criterion-error checks, the four audit cases were rerun through the full container entrypoint. The final finalizer was also replayed against the three timing/output fixture reports using the complete RewardKit detail schema; all expected rewards were preserved.
- The task's declared GPU base image imports `psutil` successfully (`7.2.2`). No GPU was allocated for this dependency check.
- Hidden queries, judgments and normalization data match the base commit. Resource documents, audit configuration, Dockerfiles and asset manifest match the pre-edit snapshot. All 13 assets had passed size/SHA-256 verification during the preceding review; they were not changed by this revision.

| Offline fixture | Successful batches | Final reward | Verifier exit | Audit healthy |
| --- | ---: | ---: | ---: | --- |
| All batches valid, accepted audit | 5 | 1 | 0 | yes |
| Two batches time out | 3 | 1 | 0 | yes |
| Three batches time out | 2 | 0 | 1 | yes |
| Two malformed outputs | 3 | 1 | 0 | yes |
| Consistent audit rejection | 5 | 0 | 0 | yes |
| Missing audit details | 5 | 0 | 1 | no |
| Contradictory audit details | 5 | 0 | 1 | no |

Evidence is under `/tmp/bingyu-legal-three-fixes-20261105-agtr9_a3/`, including `container_smoke.py`, per-case `summary.json`, evaluation/reward/detail reports, `timing-finalizer-replay.json` and source snapshots/hashes. The disposable containers used the existing local CPU verifier image `search-swe-local:bingyu-formula-verifier-20261105` with the current legal-task tests copied in. Fixtures supplied 311 synthetic queries, a ten-document corpus, a placeholder model file and an offline audit stub. A trusted fixture counter exposed the round number solely to induce selected timeouts. These are control-flow tests, not real retrieval solutions or task scores.

No new coding-agent trial, GPU model run, live audit/API request or task-image build was performed for this revision. Historical model results below do not measure the updated protocol.

Current instruction SHA-256: `b6e1fd6bc5684cb110661e7a4923f31dac4e1feb6d1b19fd4b61a3954db51a07`.

Current structured-source SHA-256: `edc896f1903d1c36464fc6582200d8347a3adbcc862d4c4bf89eae4cdfa6bcfc`.

# Local validation — 2026-10-15

Release reconciliation (2026-10-23): [recorded model run](#recorded-model-run) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

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
are recorded in [README.md](README.md) and the [instruction contract review](#instruction-contract-review). Fenced command examples
intentionally follow the user's established preference over the generic skill
rewrite convention. No arbitrary result size or regular-file restriction was
introduced. No changes were made to other tasks; four shared inventory/document
entries were extended to register this new GPU/API/audited task while preserving
pre-existing worktree changes.

## Checks performed

| Layer | Command / evidence | Result |
| --- | --- | --- |
| Task grader and judge-transport tests | `python -m unittest discover -s tasks/legal-stance-retrieval/tests -p 'test_*.py'` | 23 tests passed |
| Shared hardware/network/judge integration | `python -m unittest tests.unit.test_task_images tests.unit.test_network_policies tests.unit.test_rewardkit_deepseek` | 21 tests, 19 passed, 2 skipped because optional installed-package integration dependencies are absent |
| Runtime assets | `python scripts/assets/download_assets.py --task legal-stance-retrieval --verify-only` | All 13 current files verified, 1.14 GiB; two unused metadata files removed in v0.1.1 |
| Local staged release check | Repository `check_release(..., hf_data=..., verify_data=True, allow_unpublished=True, packages=[task])` | Zero errors; one expected unpublished-data warning |
| Normal review-stage checker | `python scripts/validation/check_tasks.py tasks/legal-stance-retrieval` | Only the three unpublished dataset revisions are rejected; no fabricated remote pins |
| Both Compose overlays | `docker compose ... config -q` with temporary base service | Passed |
| Shell and Python syntax | `bash -n tests/test.sh`, `python -m py_compile ...` | Passed |
| Diff whitespace | `git diff --check` | Passed |
| Harbor launch preview | `bash scripts/evaluation/run_task.sh --task legal-stance-retrieval --openrouter --dry-run` | Passed; no model was invoked |
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

# Source and annotation record

Upstream repository: https://github.com/idirlab/CaseFacts

Downloaded commit: `16a4072067c39daa463495e10e3bb029c29beb5b`.
The downloaded repository README identifies the paper as *CaseFacts: A Benchmark
for Legal Fact-Checking and Precedent Retrieval*, links IDIRLab/CaseFacts on
Hugging Face and advertises CC BY-NC 4.0. The collected GitHub repository metadata
has `license: null`; this is not a basis for claiming unrestricted redistribution.
Preserve the source attribution and noncommercial notice for derived data.
The source's case summaries retain Oyez URLs and original metadata. No new
court facts or precise decision dates were invented.

| Original file | SHA-256 |
| --- | --- |
| `supreme_court_cases.json` | `fbbc56fb34a0d5b2b7303d22d88699b2e6edac71d40aa09d3d5b9d230bcf47a5` |
| `train.json` | `c3bddcb5c520824cb8b6dd612830e1095bf4041e0de7b7f03cb40456aef45936` |
| `test.json` | `57823bf939cec038d813ab75d8a4a79b411e4b3207fa83f2dfbedde2d32864c2` |

The full corpus is the earlier deterministic shuffled JSONL conversion: all
3,126 source records, stable opaque IDs, all original source fields and rendered
case/term/facts/question/conclusion text. Its SHA-256 is
`5e83cadbf0d47762a1a3aadb0883aaed6ce5d155206c22b4b6c1d89523cb8fc5`.
The model card declares Apache-2.0 for Qwen3-Embedding-0.6B. Exact model file pins
and hashes are in `assets.json`.

The annotation lineage is retained outside agent mounts at
`task_development/legal-precedent-retrieval/screening/official-test-cleaning`:

- `cleaned/manifest.jsonl` accounts for every original binary test row.
- `agent-source-decisions.json` and `agent-pair-decisions.json` distinguish final
  review decisions from raw local model proposals.
- `cleaned/test/evidence.jsonl` retains accepted stance, original case text and
  reasons; `cleaned/test-cases.md` is the readable review record.
- `training-overlap-decisions.jsonl` and `test-dedup-decisions.json` record the
  reviewed proposition exclusions without removing every shared case.
- `cleaned/validation.json` and `checksums.json` preserve export verification.

Packaging copies the accepted test query/qrels bytes unchanged. Training query
rows retain only `query_id`, `query`, `stance`; original positive document-ID
seeds become binary `relevance` maps. The original training labels are not
claimed as fully corrected. An `all` training example therefore has the same
known positive seeds as its source direction, not a guarantee of exhaustive
support/refutation coverage. Training and all-mode variants remain associated
through their input IDs for agent-chosen splitting.

The 311 frozen test propositions are quality-selected, not selected for poor
model scores. Binary relevance reflects recorded majority holdings even when a
historical rule later changed. These judgments do not certify current legal
validity. All accepted positives have explicit review decisions, but unreviewed
pairs can still contain missed positives; the metric uses the frozen pooled
qrels and treats other IDs as zero gain. The original packaging step did not publish data or model assets; the later publication status is recorded below and pinned in `assets.json`.

Public packaging now uses `data/examples`. The source query ID prefix `train_` is replaced bijectively by `example_` in both examples files. Original source IDs remain in the author audit; no query text, stance, case ID or relevance map changes. The frozen hidden query IDs and qrels are untouched.

# Recorded model run

Historical result reconciled on 2026-10-23. Package versions and measurements in this section describe that saved run.

The build failed with PermissionError while the submission opened a hard-coded /tmp/court-search-*.log path. The verifier provides a writable index directory and TMPDIR. No query retrieval metric was measured; zero is the execution-failure penalty. The original result is preserved.

| Field | Observed value |
| --- | --- |
| Package at the recorded run | `0.1.2` |
| Saved agent trial version | `0.1.2` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Recorded score | 0 |
| Raw metric | nDCG@10 = Not measured (build failed) |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Recorded CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Evaluated instruction SHA-256 | `a41d40275ff625384a8b8a6d3ec422f605ace66693dd8424bc5c41bbfba7a056` |
| Saved evaluation SHA-256 | `d82a1c1b26f5b6573107efec81c6708bf422a1107373e70add3a26e2346e9c50` |
| Saved reward SHA-256 | `bb332babcb3415c07e4c5c775a4298aba3bd21c37feba0c313444cbe47862715` |

The records are retained in the author's surrounding workspace under
`task_results/legal-stance-retrieval/codex-openrouter-gpt-6-luna-max-v012-20261022T093112Z/jobs/2026-10-22__17-31-54/legal-stance-retrieval__5vakfpY/verifier/legal-stance-retrieval-eval/evaluation.json` and
`task_results/legal-stance-retrieval/codex-openrouter-gpt-6-luna-max-v012-20261022T093112Z/jobs/2026-10-22__17-31-54/legal-stance-retrieval__5vakfpY/verifier/reward.json`. These are author-local evidence
locations, not public download links. Original trajectories, submitted code,
private evaluation outputs and credentials are not published in this task.
The recorded instruction fingerprint belongs to that evaluated version. This run predates the 2026-11-05 five-round verifier revision and does not validate its behavior.

Public inputs have immutable source revisions, sizes and SHA-256 values in
`assets.json`. Unchanged published data/model references are retained.
The only new data in this release are the biomedical and filtered-ANN public
validation pairs, published through [HF PR #8](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/8) at
`234406eb7e304478e48905829fc0d3233f5a9f1f`. All 52,417 earlier dataset manifest records were preserved.
Publication does not resolve outstanding upstream licensing or independent
quality-review limitations recorded in the task's provenance.

This release reconciliation uses existing model results. It does not start a
fresh coding agent, GPU training job or paid judge call. Task-local regression
checks are recorded in the contribution PR; earlier construction and runtime records appear in the historical validation sections above.

# Instruction contract review

The table reflects the current interfaces; the notes preserve the earlier instruction-simplification decisions. This is a maintainer review record, not a runtime input.

The request uses concise prose and the two build/run command examples requested
by the user. The benchmark name and record counts are omitted.

| Public condition | Request location | Implementation |
| --- | --- | --- |
| Executable court-case retrieval; supported/refuted/all; all means either | Opening paragraph | Frozen query stances and relevance judgments |
| Corpus, examples directory and supplied model path | Inputs paragraph | Public data/model mounts |
| Runtime, model/API policy and retrieval integrity | Linked resource documents | Resource allowlist, filtered credentials, trajectory audit |
| 6-hour agent phase; /app artifacts; read-only /task and verifier /app | Submission paragraph | task.toml, mounts and submission UID |
| Executable build; 3,600 seconds; required services started in build | Build command and following sentence | build timeout; separate verifier |
| Whole query batch; 20 seconds; five fresh rounds; median-time rankings | Run command and following sentence | Five fresh build/run rounds; failed batches ordered last |
| One output per query; ten distinct known IDs; finite descending scores | Output paragraph | validate_output |
| Mean NDCG@10; build failure, fewer than three valid batches, or audit failure receives zero | Final paragraph | Deterministic metric, median selection and consistent integrity gate |

The user's explicit revision request overrides the generic instruction-rewrite
rule to copy every author-side scoring detail into the request. The numerical
baseline and reward-normalization formula are intentionally absent from the
agent prompt, but remain unchanged in the grader and author README. Annotation
scope and training-label limitations likewise remain in author documentation;
the prompt does not tell the agent to discover or repair particular data issues.
Batching and development-split suggestions were removed during that prompt simplification. Those wording changes did not introduce runtime restrictions or scoring rules; the later five-round verifier change is documented above.

The v0.1.0 instruction and validation fingerprints are preserved under the
workspace's author-only `package-build/revisions/v0.1.0-before-instruction-trim`.
Those instruction-only changes did not include a new coding-model evaluation; the later archived run is recorded separately above.

In v0.1.2, the visible data directory is `examples`, public IDs use the `example_` prefix, and resource documentation states available inputs and restrictions without suggesting a model-optimization method. The original source split and its audit records remain author-side.
