# Local validation

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

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
