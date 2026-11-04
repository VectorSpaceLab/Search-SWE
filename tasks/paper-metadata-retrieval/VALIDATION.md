# Local validation record

This file consolidates the validation history and the former `RUN_RESULTS.md`. Records retain their original dates, versions, scores, fingerprints and evidence paths. Historical uses of “current” refer to the revision described by that record, not the current checkout. The documentation consolidation on 2026-11-04 did not rerun a coding agent or judge.

The [run reconciliation of 2026-10-23](#run-evidence-reconciled-on-2026-10-23) records the available Luna result, judge health, version limits and published asset pins. Earlier validation stages are preserved below; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

This package has published, pinned public inputs and local CPU execution evidence. A configured coding-agent/live-judge trial has not been run.

## Setting and provenance

The task preserves 70,000 complete paper bodies, titles, abstracts, identifiers and original bibliographic metadata. All 70,000 original body checksums were verified during export; total body content is 4,930,665,581 bytes. The raw SQLite database is 5,212,340,224 bytes and contains one `documents` table with no precomputed search index. Collector/construction provenance is omitted from public inputs. Per-record licensing metadata remains in the database; source provenance and the contributor's additional redistribution-authorization confirmation are recorded with the HF publication.

The approved hidden set contains eight questions missed at Top-1 by all 23 measured original/Qwen configurations. Three public questions were chosen from the other twelve by fewest Qwen Top-1 hits, then lowest mean reciprocal rank across its eight configurations. The other nine questions are excluded. IDs were relabeled by split; question text and gold document IDs are unchanged. All 11 target papers are distinct. These are selected challenge cases, with source/condition and retrieved-pool alternative review; no exhaustive corpus-wide uniqueness proof or independent blind review is claimed.

Structural references: `tasks/reasoning-query-rewriting` at base revision `46197a43f8cbb364e72b6d63d5db873ae7d2cac8` for the CPU executable retrieval shape, and the user-selected local `tasks/biomedical-graph-retrieval` for its environment documents, specified resource templates, sequential unprivileged verifier and audit integration. The latter is a local reference, not assumed merged. The new task independently defines single-paper Top-1 scoring, the 3/8 split, assets and a 30-second query deadline.

## Checks actually executed

| Check | Result |
|---|---|
| Harbor `TaskConfig` schema validation | Passed |
| Export: all source body hashes, nonempty complete texts, row count, SQLite quick-check | Passed, 70,000 papers |
| Original-to-packaged split text, IDs and target-body checks | Passed, 3 validation / 8 hidden / 11 distinct targets |
| `download_assets.py --task paper-metadata-retrieval --verify-only` | Passed, all 3 files, 4.85 GiB |
| Local unpublished `check_release` with complete local staging and hash verification | 0 errors; unpublished-pins warning |
| `check_package` syntax/structure/secret/asset checks | Only the 3 expected null remote-revision errors |
| Agent and verifier Docker builds from shared CPU image | Passed |
| Both Compose overlays rendered with a base main service | Passed |
| Agent container: 16-CPU quota, 32-GiB memory, CPU-only PyTorch, 70,000 records, 3 validation examples, read-only data and absent hidden files | Passed |
| Unit tests on host and in verifier image | 12 passed in each environment |
| Submission privilege/credential/filesystem boundary checks inside disposable verifier containers | Passed |

Seven disposable verifier scenarios originally used the actual 70,000-paper database and the actual eight hidden IDs at version 0.1.0. After the user requested a 30-second query deadline, version 0.1.1 reran the 12 host/container unit tests and the actual timeout/continuation scenario against the rebuilt verifier image. The other six mechanics results below are retained from version 0.1.0; their paths and behavior are unchanged by this deadline-only revision. Their oracle fixtures were stored only in the authoring workspace, never in the task images or agent inputs. An oracle mapping is deliberately not a compliant retrieval solution; these checks validate interface, isolation and scoring mechanics only.

| Scenario | Valid primary execution | Observed reward |
|---|---:|---:|
| Oracle emits all eight gold IDs | Yes | 1.0 primary accuracy |
| Four correct / four wrong | Yes | 0.5 primary accuracy |
| All wrong, valid IDs/output | Yes | 0.0 |
| Invalid boolean score | No | 0.0 |
| Query process exits 7 | No | 0.0 |
| Third query exceeds actual 30-second deadline; other seven correct | Yes | 0.875 primary accuracy |
| Full `test.sh`, all correct but missing judge credentials | Yes primary; required audit unavailable | 0.0 final reward; nonzero exit |

The version 0.1.1 timeout test uses a 35-second sleeping query and the actual 30-second deadline. It verifies that the timed-out query's output is ignored and the remaining queries are executed. Unprivileged fixture commands also checked that private questions, labels and trajectory were unreadable; `/app`, private logs and global `/tmp` were unwritable; future query inputs were unavailable during build; and judge credentials were absent from child environments. Only the two permitted submission credentials were forwarded.

Unit tests cover malformed/missing/extra outputs, duplicate query IDs, missing/unknown/non-string document IDs, empty/multiple results, nonfinite and boolean scores, symlink outputs, wrong answers, real subprocess termination, per-query timeout continuation, fractional scoring, credential filtering and fail-closed finalization.

## Instruction equivalence and changes

Version 0.1.1 changes the per-query deadline from 120 to 30 seconds in the request, structured specification, metadata, grader and tests. It preserves the 120-minute implementation budget, 1,800-second build budget, fixed data and labels. Current deadline-specific evidence is under `scale-70k/author/task-package/revision-v011/`.

The final `instruction.md` was checked against `raw-instruction.md`, `task.toml`, resource docs and verifier for the objective, inputs/schema, all CLI flags, artifact transfer, non-root/read-only execution, CPU/memory/storage/time limits, API restrictions, per-query timeout semantics and scoring/failure behavior. No source collection name, target titles/IDs, baseline-derived hints or prescribed retrieval algorithm appears in the agent request. The generic CPU environment document matches the shared image. The API templates and host allowlists match the user's requested configuration.

An initial author-test stub omitted an elapsed-time field returned by real subprocess execution. The stub was corrected; all final unit and container checks use the unchanged grader timing contract. No scoring threshold or query was changed in response to a low model score. No coding-agent score exists for this new CPU task.

## Evidence and remaining layers

Construction, split selection, content hashes, build logs, CPU probes, runtime reports and author-only fixtures are retained outside the task package under the authoring workspace's `scale-70k/author/task-package/`. `assets.json` pins the three public inputs to official dataset revision `8ee1f03ffe70dd7eb57b0bcd8627730fc4232dd3` with the original sizes and hashes. The publication changed only source paths/pins and author-facing records; paper bodies, questions, labels, instructions and runtime remain unchanged.

No paid coding-agent run, live OpenRouter/Jina functional probe or live DeepSeek trajectory audit was run for this package. The earlier Qwen retrieval/reranking measurements are authoring evidence, not a coding-agent trial in this CPU environment. Local authoring does not authorize paid model calls or remote publication; see `.agents/skills/create-searchswe-task/SKILL.md` and its model-evaluation reference for those separately scoped steps. Neither the oracle fixtures nor the unit-level judge stubs establish an end-to-end agent score or provider availability. The public data were subsequently published through [the HF contribution](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/6); its observed official merged revision is `8ee1f03ffe70dd7eb57b0bcd8627730fc4232dd3`. Hidden inputs, model weights and author solutions are excluded.


## Publication verification (2026-10-21)

The three public data files were published through [the HF contribution](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/6)
and pinned to observed official merged revision `8ee1f03ffe70dd7eb57b0bcd8627730fc4232dd3`.
The official manifest preserves all 52,288 preceding records and adds exactly
the three reviewed runtime assets. Their remote LFS sizes and SHA-256 values
match the task manifest. A fresh external output directory and cache restored
all three files with the repository downloader; size and SHA-256 verification
passed, 3 files / 4.85 GiB. The corpus, split, instructions, 30-second deadline
and grader are unchanged. The prior CPU/container mechanics evidence therefore
still applies. The 12 task contract tests passed again; shared-image,
network-policy and RewardKit-configuration checks ran 20 tests, with 18 passes
and 2 host-dependency skips. No additional paid coding-agent/API trial was run.

## Run evidence reconciled on 2026-10-23

The v0.1.1 verifier completed all eight queries with valid outputs, no query timeouts and a passing audit, scoring 0/8. This is a valid low retrieval score. A compliant positive-result reference under the final runtime contract and independent label/alternative-answer review remain validation gaps.

| Field | Observed value |
| --- | --- |
| Current package | `0.1.1` |
| Saved agent trial version | `0.1.1` |
| Agent / model / effort | Codex / OpenRouter `openai/gpt-6-luna` / `max` |
| Evidence type | Saved formal verifier result |
| Current available score | 0 |
| Raw metric | Accuracy@1 = 0 |
| Archived final reward | 0 |
| Required trajectory judge | Succeeded; numeric pass = 1 |
| Current CPU / RAM / GPU configuration | 16 CPUs / 32768 MiB / 0 GPU(s) |
| Development limit | 7200 seconds |
| Current instruction SHA-256 | `6dbf8e9b1226419e87c86524368e6d459b0fc2661dc361d0daaca57f0b70e440` |
| Saved evaluation SHA-256 | `b8eab2a81b24b5e7af92c5802fed7934b40a3b423becc084ed51ad3e04f19ad2` |
| Saved reward SHA-256 | `e51c8aa464a110f769a86cc20898314713b79b8d93a77a325a34684b994d6aaf` |

The records are retained in the author's surrounding workspace under
`task_results/paper-metadata-retrieval/codex-openrouter-gpt-6-luna-max-v011-20261022T093112Z/jobs/2026-10-22__17-31-54/paper-metadata-retrieval__te9Wvwy/verifier/paper-metadata-retrieval-eval/evaluation.json` and
`task_results/paper-metadata-retrieval/codex-openrouter-gpt-6-luna-max-v011-20261022T093112Z/jobs/2026-10-22__17-31-54/paper-metadata-retrieval__te9Wvwy/verifier/reward.json`. These are author-local evidence
locations, not public download links. Original trajectories, submitted code,
private evaluation outputs and credentials are not published in this task.
The current instruction matches the evaluated instruction; where public data,
normalization or verifier behavior changed, the limitations above apply.

Public inputs have immutable source revisions, sizes and SHA-256 values in
`assets.json`. Unchanged published data/model references are retained.
The only new data in this release are the biomedical and filtered-ANN public
validation pairs, published through [HF PR #8](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/8) at
`234406eb7e304478e48905829fc0d3233f5a9f1f`. All 52,417 earlier dataset manifest records were preserved.
Publication does not resolve outstanding upstream licensing or independent
quality-review limitations recorded in the task's provenance.

This release reconciliation uses existing model results. It does not start a
fresh coding agent, GPU training job or paid judge call. Task-local regression
checks are recorded in the contribution PR; earlier construction and runtime
records are preserved above.
