# Validation: instruction-following-embedding

## Review scope (2026-11-05)

This revision preserves the E5 query-only LoRA interface, 512 KiB deployment limit, fixed document tower, 20/84 public/hidden split, six relevance gates and harmonic p-MRR reward. It removes GPU model/capacity assumptions and RAM-backed workspaces, measures each query version five times using its median duration, standardizes public validation data under `data/validation`, restores processed training data through the asset manifest, and aligns metadata with the existing FollowIR-7B calibration.

Reference packages: `tasks/biomedical-graph-retrieval` for pinned public validation assets and read-only mounts; `tasks/protein-text-bidirectional-retrieval` for the single-GPU package structure. Environment documentation follows `docker/gpu/environment.md` and this task's actual Dockerfiles. Other tasks and shared infrastructure are outside this change.

The agent and verifier retain 16 CPUs, 32 GiB RAM, 32 GiB total task storage and one GPU. CUDA/BF16/SDPA support, document batch sizing and Landlock host compatibility are not redesigned or newly certified. Document preparation runs once. Query measurements include encoding, transfer, normalization and complete candidate ranking; timed-out measurements remain in the five-sample population. Malformed output and model/resource violations are not made acceptable by repetition. Only the existing compliance audit uses an LLM; its repetition policy is unchanged.

## Checks completed

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tasks/instruction-following-embedding/tests -p 'test_*.py' -v`: 63 discovered, 53 passed, 10 container/GPU-only tests skipped on the host. New timing/resource regressions cover median selection and its ranking, two versus three timeouts, ranking work inside the timer, invalid vectors, global resource/model failure, the single-GPU count requirement and `/tmp` storage accounting.
- Built both task Dockerfiles successfully as `search-swe-local:ife-review-20261105-environment` and `search-swe-local:ife-review-20261105-verifier`.
- Ran the same suite in the disposable verifier container with 2 CPUs, 8 GiB RAM, no network, `NVIDIA_VISIBLE_DEVICES=void`, a read-only `/task/runtime` mount, and `SEARCH_SWE_SANDBOX_TEST=1`: 63 discovered, 58 passed, 5 GPU-only tests skipped. This includes positive fixed-format/model-manifest cases, invalid model submissions, reward/audit failures, archive traversal rejection, and actual Landlock/seccomp read/write/network/UID boundaries on this host. No task isolation or UID cleanup was run on the shared host.
- A separate disposable agent-container smoke check confirmed `/app` and `/tmp` use `overlay`, performed a submission archive roundtrip on disk, read exactly 1,717 train records and 20 validation groups, rejected writes to the validation mount, and confirmed hidden groups were absent.
- `python3 scripts/validation/check_tasks.py tasks/instruction-following-embedding`: 0 errors. `python3 scripts/validation/check_release.py`: 0 errors, 0 warnings. `bash -n tasks/instruction-following-embedding/tests/test.sh` and scoped `git diff --check` passed.
- Parsed the Python sources, TOML, both Compose files and asset metadata. Agent instruction and docs use unwrapped paragraphs; both Compose files preserve a single GPU and omit tmpfs. Reviewed instruction/source equivalence for the serving format, fixed document tower, validation-only supervision, payload/relevance limits and revised timing/storage rules. The instruction names the median limit; sampling/failure implementation details stay in the author contract and runtime.
- Verified the original 20/84 public/hidden group counts, disjoint group keys and 1,000 distinct candidates per public group. Processed training output matches the audited size and hash, checked against the preparation specification before its removal. All 20 public groups match the corresponding MIT-labelled MTEB releases in query/instruction text, candidate membership, both relevance maps and changed-document membership; task bytes and candidate ordering are unchanged. See `DATA_SOURCES.md`.

## Calibration and budget

The existing `tests/scoring_parameters.py` remains unchanged (SHA-256 `9399999b74f7ade628b8a9ddce494d49b3a27ec8c02bd42f6220b9aba9203960`). Metadata now agrees with its `B=0`, `U=0.10647366293851011`; the diagnostic arithmetic mean is `0.12869108334248824`. Both reference values were verified against `../task_development/instruction-following-embedding-followir7b-calibration-20261104T064729Z/metrics.json`. This is an existing external reranker reference, not a new calibration or theoretical upper bound.

The 5,000-second primary window covers one preparation of at most 3,600 seconds plus 840 one-second query measurements, leaving 560 seconds for primary overhead/recovery. The primary, audit and finalizer wrappers including kill grace total 7,015 seconds within the unchanged 7,200-second verifier limit. Full repeated failure recovery remains bounded by that primary window; it is not an unbounded retry mechanism.

## Published assets

[Hugging Face community PR #10](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/10) is merged. The two processed assets are pinned to official commit `1758c2ec5bd9678a5284bbf1875c57999cc0eb81` in `assets.json`. All 52,409 prior official manifest records were preserved, with exactly two additions. Existing upstream and model pins are unchanged. Remote dataset metadata was compared with the reviewed staging before merge; provenance and license notices accompany the assets.

Both new assets were restored through the repository's `scripts.assets.download_assets.restore` implementation into a fresh output directory using an empty Hugging Face cache, then rechecked in verify-only mode. Their sizes and SHA-256 values match `DATA_SOURCES.md` and the local task bytes. Only after this check was the old tracked `environment/public/dev-groups.json` copy removed. Publication/restore receipts are under `/tmp/ife-review-20261105-hd0q_pn4/`; the durable contract is the pinned `assets.json`, source record and HF PR.

## Runtime data cleanup

Removed the raw preparation directory and its 17 non-runtime manifest entries, together with the unused preparation script/specification. The three required corpora now restore to `data/corpus/{robust04,core17,news21}.jsonl`; both Compose files map these files to the existing `/task/corpus/` interface. Copied the locally available corpus bytes from the release checkout into these destinations and verified all three original sizes and SHA-256 values. The manifest now contains five task data files and ten unchanged model files. Processed training/validation bytes, remote pins, grading code and the agent-visible data interface are unchanged.

## Instruction concision

The instruction was shortened to task requirements, input locations/counts, submission format, fixed serving behavior, scoring criteria and resource limits. Training recipes, baseline-cache advice, precision-saving tips, submission strategy and repeated explanations were removed. The training-supervision rule remains the user-specified single sentence. The compact p-MRR expression `(y - x) / max(x, y)` is algebraically equivalent to the previous two cases. All six relevance floors and the existing deployment/resource limits are preserved. This prose edit was checked for paragraph formatting and whitespace; it does not change evaluator code.

## Remaining runtime validation

No new coding-model trial, real GPU inference/throughput benchmark or live compliance-audit API run has been performed for this revision. Consequently there is no new model score, trajectory or live judge-health result. Full model restoration was not repeated; all five task data files have been verified. CUDA/BF16/SDPA/document-batch compatibility and the historical preparation/query limits still require validation when deploying to different hardware. The container isolation checks establish compatibility only for the current host.

Instruction SHA-256: `8cfda1816312e5069c3c8336e37cce0fc6f722f900e321e2e098afbef76022de`. Runtime evaluator SHA-256: `5b5c0537a0828fd81d400af1b3fc15117998e70debf35ac318df2bbe37b3b2c1`.

## Retained-file storage fix — PR #47 second review

The 32 GiB disk budget now counts named files together with backing files retained by file descriptors or memory mappings. All submission-UID processes are inspected, including detached descendants; same-UID development processes are included as well. Additional references to one device/inode do not multiply its charge, while existing named-hardlink accounting is preserved. A 4 KiB partial mapping still charges the full logical size of its backing file. Anonymous memfd files are counted too. Sampling failures for live processes become global `ResourceViolation` errors, and usage is checked before worker cleanup and before the final resource report.

The implementation reuses the storage-accounting approach already verified in `multilingual-vector-postprocessing`, with this task's existing 32 GiB limit, fixed input roots and writable paths. Both phases mount the same runtime directory. Both Compose overlays declare `CHECKPOINT_RESTORE` for the trusted supervisor, and isolation restores nonroot procfs visibility after dropping privileges. Real child processes assert UID 10001 and zero effective/permitted capabilities. The existing filesystem, network, ptrace and process-memory restrictions remain active.

| Check | Observed result |
| --- | --- |
| New FD-only and mmap-only regressions against the previous implementation | Both failed: the named 40 GiB files were rejected, but unlinking them caused the old checker to accept them. |
| Original second-review reproduction script, unchanged, with the corrected runtime and supervisor capability | Now raises `ResourceViolation: 32 GiB task storage exceeded` after unlink and closure of all descriptors. The payload retains two 20 GiB files through libc mappings of only 4 KiB each. |
| Disposable offline container: `python -B -m unittest discover -s . -p 'test_*.py' -v` | 73 discovered, 68 passed, 5 GPU-only cases skipped. Includes 10 new actual-isolation storage cases covering FD-only, mmap-only, partial mappings, memfd, reference deduplication, release races, inaccessible live processes and the final reporting check. |
| Actual Compose configurations through the merged repository runner validator | Both phases of this task and multilingual-vector-postprocessing accepted. The branch includes main commit `d7bf57ae1c709d495490198ab9401ddfafd24943`, which supplies the supervisor-capability startup compatibility. |
| Static checks | This task's merge-ready check reports 0 errors; the whole-repository release check reports 0 errors / 0 warnings; `git diff --check` passes. |

Evidence is under `/tmp/bingyu-pr47-ife-storage-fix-20261105-_p5mbwml/`: `before-fix.log`, `task-tests.log`, `original-review-reproducer.json` and the rendered Compose configurations. The tests use a cached verifier image, read-only current source, no network, no credentials and no GPU allocation; sparse files do not physically write 40 GiB. No full model encoding/scoring run, GPU trial or live compliance judge was executed. Scoring, instructions, data, model assets and existing time limits are unchanged. Storage remains sampled logical-byte accounting rather than an instantaneous filesystem quota.
