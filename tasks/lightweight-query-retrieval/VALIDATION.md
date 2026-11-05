# Local validation

## Review update — 2026-11-05

The current contract specifies one GPU without a model or memory capacity. Query timing now uses five fresh service instances and their median duration; the index is still built once, and every run must pass the existing quality gate. The retrieval supervisor is 2,900 seconds and the overall verifier limit is 4,500 seconds. The candidate-stage maximum is `1200 + 5 * (120 + 60 + 120) = 2700` seconds, leaving 200 seconds inside the retrieval supervisor. Retrieval, audit and finalization supervisors plus their termination grace periods total 4,260 seconds, leaving 240 seconds for outer setup and cleanup. The environment document's compatibility explanation is shortened.

Input files, public-example layout, model weights, the 0.45 quality gate, the 0.8-second zero-credit point and the single integrity audit are unchanged. Historical hardware and three-run measurements below describe their original runs; they are not five-run measurements of this revision.

Checks executed: `python -B -m unittest -v test_contract test_final_gate test_timing` from `tests/` passed all 22 tests. The new fixtures exercise the production evaluation loop with simulated services and build execution, covering one build, five fresh scratch directories, five-sample median scoring, fifth-run quality failure and nested timeout coverage. The task static validator reported zero errors; `bash -n tests/test.sh` and task-scoped `git diff --check` passed. No full GPU retrieval run or live integrity-audit call was performed for this revision.

Release reconciliation (2026-10-23): [recorded run evidence](#run-evidence-reconciled-on-2026-10-23) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

## Run evidence reconciled on 2026-10-23

This section preserves the historical v0.4.0 evaluation. Its version, hashes and results refer to that run, not the current five-run revision.

The v0.4.0 verifier and live integrity audit completed. Macro nDCG@10 was 0.4303102260205993, below the 0.45 gate; median query-batch time was 0.41057249531149864 seconds. The zero is therefore a quality-gate result. A positive-reward final-configuration witness and live adversarial audit calibration remain unestablished.

| Field | Observed value |
| --- | --- |
| Evaluated package | `0.4.0` |
| Saved agent trial version | `0.4.0` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Recorded score | 0 |
| Raw metric | macro nDCG@10 = 0.430310226020599 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Evaluated CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 1 GPU(s) |
| Development limit | 21600 seconds |
| Evaluated instruction SHA-256 | `dea7762c163c98d43a21e3eabfa516d2627d704677c54883421bfdb38f13fc8e` |
| Saved evaluation SHA-256 | `c8b5676b33232e8f892f892c93c2ea2137500055032fa5c7e6e5faad96601fcb` |
| Saved reward SHA-256 | `b968c26c370deb6b29fd210d9bb4206f1d14d34014734d2e39c29cc440dd5501` |

The records are retained in the author's surrounding workspace under
`task_results/lightweight-query-retrieval/codex-openrouter-gpt-6-luna-max-v040-20261022T135859Z/jobs/2026-10-22__21-59-35/lightweight-query-retrieval__NXt6iHq/verifier/report.json` and
`task_results/lightweight-query-retrieval/codex-openrouter-gpt-6-luna-max-v040-20261022T135859Z/jobs/2026-10-22__21-59-35/lightweight-query-retrieval__NXt6iHq/verifier/reward.json`. These are author-local evidence
locations, not public download links. Original trajectories, submitted code,
private evaluation outputs and credentials are not published in this task.
At the 2026-10-23 reconciliation, the instruction matched the evaluated instruction. Later changes, including the current five-run protocol, are recorded separately above.

Public inputs have immutable source revisions, sizes and SHA-256 values in
`assets.json`. Unchanged published data/model references are retained.
The only new data in this release are the biomedical and filtered-ANN public
validation pairs, published through [HF PR #8](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/8) at
`234406eb7e304478e48905829fc0d3233f5a9f1f`. All 52,417 earlier dataset manifest records were preserved.
Publication does not resolve outstanding upstream licensing or independent
quality-review limitations recorded in the task's provenance.

This release reconciliation uses existing model results. It does not start a
fresh coding agent, GPU training job or paid judge call. Task-local regression
checks are recorded in the contribution PR; earlier construction and runtime records are retained below.

## Integrity judge integration — 2026-10-22, version 0.4.0

Instruction SHA-256:
`dea7762c163c98d43a21e3eabfa516d2627d704677c54883421bfdb38f13fc8e`.
This revision implements the user's requested trajectory audit after PR #23's
finding that the numerical grader alone could reward a precomputed answer table.
The source instruction and rewritten request both disclose the final integrity
gate. Assets, original nDCG gains, the 0.45 quality threshold, 0.8-second anchor,
three timing runs and all candidate execution limits are unchanged.

### Implementation and reference patterns

- Transfer `/logs/agent/trajectory.json` alongside `/app`, protect it from
  candidate code, and inspect both with the pinned RewardKit 0.2.0 / DeepSeek
  V4.1 Flash judge. The rubric prohibits hidden-answer mappings and outside
  resources while allowing legitimate corpus indexes, token lookup, training,
  learned parameters and preprocessing. Poor retrieval alone is not a violation.
- Keep raw retrieval in `report.json` and judge output in `.private/`. Public
  reward files stay zero until finalization. Only a successful audit with numeric
  binary pass can release the original retrieval reward; missing/malformed
  evidence, failed processes and invalid judge values fail closed.
- Permit OpenRouter only in the verifier phase. Candidate commands still use a
  clean environment, now with an inherited seccomp socket filter and UID drop.
  No candidate receives judge keys or proxy variables. Agent execution remains
  offline. The wrapper permits Unix-domain sockets needed by local libraries.
- Extend the overall verifier timeout from 2,400 to 3,900 seconds for the audit.
  Retrieval's 2,300-second supervisor and candidate build/load/query limits are
  unchanged. The audit has a 1,260-second supervisor and finalization 60 seconds.

The reviewed `memory-constrained-dense-retrieval` package at repository base
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8` supplies the offline-submission /
root-side-audit pattern. The existing local `filtered-ann-retrieval` wrapper
supplies the seccomp-before-UID-drop pattern. The DeepSeek backend is byte-identical
to the repository wrapper. Task-specific grading and allowed training resources
were retained; the finalizer strictly rejects boolean/string/nonbinary decisions.
Only this task and its directly necessary shared network/judge inventory entries
were changed for this integration.

### Executed local checks

| Check | Result |
| --- | --- |
| Host contract and final-gate tests | 19 passed; 2 container-only tests skipped |
| Disposable CPU container tests | 21 passed, 0 skipped |
| Built task verifier image, without GPU devices | Current runtime files matched the workspace byte-for-byte; 21 tests passed, 0 skipped |
| Real subprocess isolation | UID 10001, no-new-privs, protected trajectory/judge files, filtered credentials; IPv4/IPv6 socket creation denied, including a child exec; Unix socketpair allowed |
| Actual `test.sh` with controlled executables | 14 scenarios passed: valid pass/rejection/zero, malformed/nonbinary outputs, grader/judge failure, timeout exit status, missing credentials/trajectory, stale judge output and finalizer failure after a partial write |
| Numerical gate | Fractional raw reward preserved on pass; no positive public reward before audit; booleans, strings, fractions, out-of-range values, duplicate JSON keys and nonfinite outputs rejected |
| Verifier Dockerfile build | Passed using the existing GPU base and cached pinned judge dependencies; no GPU allocated |
| Harbor schema/network plan | Passed: agent baseline and execution offline; verifier allowlist exactly `openrouter.ai`; trajectory declared as an artifact |
| Canonical judge wrapper | Byte-identical to the existing repository wrapper |
| Task static and selected-package release checks | 0 errors, 0 warnings |

The container-only tests require explicit `SEARCH_SWE_RUN_CONTAINER_TESTS=1`
inside a disposable root container; they replace fixture executables temporarily
and must not be run against host `/app`, `/tests` or `/logs`.

The selected shared-image/network/RewardKit suite ran 14 tests: nine passed,
two host-dependency skips and three inventory failures. The remaining failures
are the pre-existing unregistered `paper-metadata-retrieval` package in the
local shared inventories (including the task-count assertion), not lightweight's
new settings. The task's exact Harbor phase plan and wrapper were checked
separately. No unrelated task was registered or altered to suppress those failures.

### Limits and remaining evidence

All judge decisions in the local shell/gate tests are supplied by test fixtures.
The answer-table rejection case proves that a judge rejection cannot be bypassed
by a positive retrieval score; it does **not** prove a live model detects the
table. Likewise the allowlisted legitimate artifacts in the rubric have not yet
been accepted by a live judge. Live adversarial/legitimate judge validation,
the final-version coding-agent trial and a new GPU retrieval run remain unrun.
No paid API call, GPU execution or publication was performed for this revision.

The 0.3.0 witness below remains historical numerical-retrieval evidence; it does
not validate the new prompt, process wrapper or integrity judge. Its zero reward
is preserved. A future live audit needs `VERIFIER_OPENAI_BASE_URL` and
`VERIFIER_OPENAI_API_KEY` configured locally, plus a scoped run budget.

Commands, logs, source hashes and the local patch are retained outside the task
under `task_development/lightretriever/judge-integration-20261022/`. These are
local author records, not publicly hosted evidence or a completed audited trial.

## Historical retrieval validation — version 0.3.0

Task version: 0.3.0. Author: Bingyu. This records local execution evidence and
the subsequent official asset pins. It is not a configured coding-agent trial.

## Reviewed structure and artifacts

Reviewed `tasks/query-encoder-alignment` at repository base
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8`, plus the local
`methodology-inspiration-retrieval` and `decision-model-training` packages.
Reuse covers the shared GPU image, separate verifier and mount/protection
patterns. This task instead measures complete batch retrieval time after a
quality gate, allows corpus indexing, and supplies no reference implementation.
The user's requested fenced command examples are retained; the complete
raw-to-rewritten correspondence is in `instruction-audit.json`.

Only this task and the required GPU/network-policy inventory entries were added.
Source data, preparation scripts, trained checkpoints, indexes and measurements
are in `../../../task_development/lightretriever`, outside the solver package.

## Inputs and legal feasibility witness

The exact 80,000-example sample covers all 23 original sources. The original
query/positive/negative texts are preserved. One normalized exact test-query
overlap was replaced from its own source; zero remain. Sampling provenance,
source revisions, sizes and checksums are recorded in `sampling-report.json`,
`examples-audit.json` and `final-sample-provenance.jsonl` in the authoring folder.
All nine supplied model files match the pinned original Meta Git/LFS objects;
see `model-integrity.json`. The author-trained LightRetriever adapter is absent
from all solver and verifier mounts.

The final witness uses `checkpoint-500`, trained on 62,907 distinct
examples from the supplied sample, from the original Llama-3.2-1B base.
The checkpoint's training loop took 2963.26 seconds on
one A100 40GB with 16 CPUs and a 32 GiB container limit. The input-membership
and adapter checksums are recorded in `calibration/checkpoint-500-input-audit.json`.
This is a feasibility run with a reduced dataset, not reproduction of the
authors' full training experiment.

A complete one-pass run over all 80,000 supplied examples also finished on one
A100: 3,773.43 seconds for the training loop, 3,857.96 seconds including
preparation, 20.40 GiB peak PyTorch CUDA allocation and 4.03 GiB peak host RSS.
See `calibration/trained-witness/report.json` and `full-training-input-audit.json`.
The final scored artifact deliberately uses the already-calibrated checkpoint
listed above; the later full-epoch checkpoint is not substituted into these scores.

The complete corpus index was constructed inside the task GPU image under the
same one-GPU/CPU/RAM limits. Its construction log is
`calibration/checkpoint-500-build.log`. The witness transfers that independently
built index as an artifact and copies it during the verifier build phase;
the copy time in the verifier report is not claimed as corpus encoding time.
Training, preprocessing and original index construction fit the six-hour
development budget. Retrieval variants were checked against a separate, frozen
300-query author development set. The original hidden workload was used for
task calibration, not as training data. Model training did not use hidden
questions or relevance judgments.

## Complete workload measurements

| Implementation | Minimum macro nDCG@10 | Median seconds, 1,271 queries |
| --- | ---: | ---: |
| checkpoint-250 / bm25 | 0.421111 | 0.512044 |
| checkpoint-250 / full | 0.473451 | 0.959254 |
| checkpoint-250 / lookup-bm25 | 0.442673 | 0.650280 |
| checkpoint-250 / routed | 0.456275 | 0.840109 |
| checkpoint-500 / full | 0.495216 | 0.897636 |
| checkpoint-500 / lookup-bm25 | 0.454410 | 0.452994 |
| Final configured witness | 0.454410 | 0.860873 |

Comparable formal measurements used GPU 1, an NVIDIA A100-SXM4-40GB, with
`--cpus 16 --memory 32g --network none`. Each row uses three fresh services,
24 public-example warm-up queries, shuffled hidden requests with fresh IDs,
and the complete original 1,271-query test workload. Reported quality is the
minimum of the three macro values; time is their median. Timing includes pipe
transfer, query processing, search, ranking, response transfer and JSON decoding.
The final row uses the actual frozen gate and time anchors; earlier calibration
rows used neutral bounds solely to collect measurements, so their provisional
reward fields are not task scores.

Full per-run times are retained. Some earlier CPU-heavy variants had a single
large timing outlier; these are not deleted. The specified three-run median
handles one outlier. Final evidence: `witness-runs/lookup-500-anonymous/result.json`
and its `logs/` directory. The run completed validly and passed the quality gate;
observed reward is **0.000000**.

## Current scoring and collection identifiers

The scoring rule introduced in version 0.2.0 uses a quality gate of 0.45 and
`max(0, 1 - T / 0.8)`; version 0.3.0 retains it.
One is a theoretical zero-runtime upper bound, with no positive-time full-credit
interval. Original measurements and their original rewards remain archived under
their original scoring rules. For example, the prior witness's measured
0.4581157081 seconds and quality 0.4544096731 rescore to 0.4273553649.
This is an arithmetic replay, distinct from the new final run above.

Runtime collection labels are now `corpus1`, `corpus2` and `corpus3`. A bijective
renaming is applied to the corpus, hidden queries, qrels and warm-up records.
Per-collection candidate scopes, text, IDs and relevance grades are unchanged.
The 80,000-example file has no collection field and remains byte-identical.
The full row comparison and updated checksums are recorded in
`collection-aliases-0.3.0/data-audit.json`.

Contract tests and the complete separate-verifier witness were rerun with the
anonymous collection labels. The data manifest and local staging were refreshed.
Existing image, numerical-metric and isolation evidence below is retained for
the unchanged runtime, scoring logic and protection boundaries.

The anonymous-label rerun retained exactly the same retrieval quality as the
previous run. Its observed timing is retained even when it earns zero under
the strict speed rule; label renaming is not a timing improvement. No timing
result was discarded or replaced to obtain a positive score.

The subsequent instruction-only edit removes the domain enumeration, explicit
score formula and theoretical zero-time explanation. It retains the quality
gate, zero-score time anchor and all execution requirements. Grader and input
bytes are unchanged; no new GPU run was needed for this wording edit.

## Other executed validation

- Eleven mounted asset files passed size and SHA-256 verification.
- Both Compose overlays parsed; agent and verifier images built successfully.
- The actual agent image completed CUDA forward, backward, optimizer and adapter-save checks.
- Twelve scoring/contract unit tests and fifteen disposable-container protocol,
  failure and isolation fixtures passed. Fixtures that know gold are only grader
  tests and are not used as the legal retrieval feasibility witness.
- Graded nDCG matched `pytrec_eval` on 300 questions within 2.23e-16.
- Targeted shared-image and network-policy integration tests passed.
- Local release inspection with staged unpublished data has no errors and one
  explicit publication warning. At that local validation stage, `check_tasks.py` rejected the two
  unpublished derivative data revisions. The publication update below supersedes
  that asset-pinning limitation.
- Launcher dry-run configuration was checked. No paid model call was made.

Logs and receipts are retained in the authoring folder. The complete repository
unit-suite attempt was interrupted while waiting for an asyncio executor to
shut down; it is not claimed as a successful full-suite run. No unrelated
repository code was changed to bypass that condition.

## Unrun layers and release state

No complete configured coding-agent trial was executed, consistent with the
user's earlier preference to deliver the package without an extra paid trial.
The authoring skill treats that as a separate release-validation layer; the
legal witness and fixture tests do not replace it. There is no model-trial
feedback to claim. The original local checks preceded publication. Both derived
assets are now pinned to official dataset revision
`ff16485accd6d258610c158fce45e36b50a47c3f`; their official sizes and SHA-256
hashes match the locally validated inputs. Original model pins are unchanged.

The original local package is identified by `final-package-fingerprint.json`
in the authoring folder, including each package text/private-evaluation-file hash.
The final witness's copied grader and scoring files must match those fingerprints.

## Publication verification (2026-10-21)

The two official public data files were restored into a fresh external output
directory and cache with the repository downloader. Both size/SHA-256 checks
passed: 2 files, 2.19 GiB. The original model revision and all model hashes are
unchanged. A local verification of both new packages also passed all 14 asset
checks, 9.35 GiB including the original model and paper database.

The current package passes `check_tasks.py tasks/lightweight-query-retrieval
--merge-ready --base 11a170be17a648511233e69a8ce1a9ae756aa0d9`.
Its 12 contract tests passed again. On that latest main base, shared-image,
network-policy and RewardKit-configuration checks ran 20 tests: 18 passed and
2 skipped because the host does not have harbor-rewardkit 0.2.0 installed.
No shared repository file needed an edit: current tests discover tasks
automatically. These publication changes affect paths, pins and author-facing
records; input hashes, instruction, runtime and scoring are unchanged, so the
existing GPU feasibility evidence remains applicable. No new paid model or
GPU trial was run.

## Third-party materials

This local task is Built with Llama.

- **Llama 3.2 1B**, Meta: original model revision
  `4e20de362430cd3b72f300e6b0f18e50e7166e08`.
  [Original model](https://huggingface.co/meta-llama/Llama-3.2-1B).
  The model's Llama 3.2 Community License and Acceptable Use Policy are retained
  in `models/Llama-3.2-1B/LICENSE.txt` and `USE_POLICY.md`. They are separate from
  the repository's software license. The weights were obtained from the
  [ModelScope LLM-Research mirror](https://modelscope.cn/models/LLM-Research/Llama-3.2-1B)
  and verified against the original Hugging Face LFS pointer. No author-trained
  retrieval adapter is supplied to the agent.
- **LightRetriever fine-tuning data**, Guangyuan Ma et al., revision
  `840793a0229ead35a9c820e9803092c3f1383e07`:
  [author release](https://huggingface.co/datasets/lightretriever/lightretriever-finetune-data).
  Its dataset card declares Apache-2.0. The 80,000 examples are a sampled
  derivative of the original 23-source experiment configuration. Original
  query, positive-passage and negative-passage contents are preserved. The
  upstream collections retain their respective rights and attribution
  requirements; the author's aggregate license does not replace those rights.
- **BEIR-formatted SciFact, NFCorpus and FiQA**:
  [SciFact](https://huggingface.co/datasets/BeIR/scifact),
  [NFCorpus](https://huggingface.co/datasets/BeIR/nfcorpus), and
  [FiQA](https://huggingface.co/datasets/BeIR/fiqa).
  These BEIR release cards declare CC-BY-SA-4.0. Preserve that license and the
  original dataset attributions for the derived corpus and evaluation records.
  Transformations are ID renaming and anonymous collection tags; original text, candidate
  universes, split membership and relevance grades are retained.

The original datasets are SciFact (Wadden et al., 2020), NFCorpus (Boteva et al.,
2016), and FiQA (Maia et al., 2018), distributed for retrieval evaluation by
BEIR (Thakur et al., 2021). This task does not introduce new relevance labels.

The public corpus and example files are published in `search-swe/Search-SWE`
at revision `ff16485accd6d258610c158fce45e36b50a47c3f`; see the task asset
manifest and the official dataset provenance. Model files remain pinned to the
original gated upstream repository. Publication does not replace source terms.
