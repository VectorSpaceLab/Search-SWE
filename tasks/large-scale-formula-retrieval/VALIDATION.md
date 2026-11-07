# Timing, isolation and layout revision — 2026-11-05

Base commit: `783d2eeafd580f64c404da94dfc05733811d5c0f`. This revision is limited to `large-scale-formula-retrieval`. The following dated sections describe earlier revisions, not the current verification protocol.

## Changes and preserved constraints

- Build once, then run five complete serving passes in a fixed query order. Each pass starts fresh processes and an empty runtime directory, using the same completed read-only index and three-query warmup. The operating-system file cache is not flushed. For each query, select the third attempt after sorting successful attempts by elapsed time and placing failures last; score that attempt's response. Ties use pass order. Fewer than three valid responses within 50 ms gives zero for that query. A response is never selected by relevance score.
- Run the single compliance audit as UID 10002 with a filtered environment and inherited Landlock restrictions. It can read the protected trajectory and submission, write its own scratch/output, and cannot read hidden judgments or modify numerical reports. Aggregate, raw and normalized audit decisions must agree. Rejection is a valid zero; an incomplete or inconsistent audit is an infrastructure failure. There is no answer-quality LLM judge in this task.
- Use the shared CPU environment template and concise phase-specific resource instructions. The allowed API providers and generative model IDs are unchanged; only development and the timed build may call them. Agent-facing Markdown has one source line per paragraph. The instruction explicitly describes the verifier's existing score sorting and the read-only submission directory.
- Restore public corpus files directly into `data/`, and queries/judgments into `data/validation/`. All six existing official HF sources, immutable revisions, sizes and SHA-256 hashes are preserved. No dataset was republished. Host filesystem-tool caches now live outside public inputs.
- Remove the `80,81` CPU fallback from both Compose overlays. The existing standard launcher selects two available logical CPUs and supplies `FORMULA_CPUSET`; caller-managed launches must supply that variable. The task still requires native Linux x86_64, FUSE-backed bounded storage and Landlock support. This does not guarantee equal 50 ms performance on different CPUs.
- Preserve 2 CPUs, 4 GiB RAM, 64 GiB total task storage, no GPU, the 34 MiB prepared-artifact limit and the physical 40 MiB serving filesystem. No production tmpfs was added or substituted for the serving filesystem. nDCG-prime calculation, all 76 hidden queries, hidden judgments and the source manifest are unchanged.

The audit isolation follows the existing task-local pattern in `khmer-embedding-training`; CPU documentation follows `docker/cpu/environment.md`; validation placement follows the repository's `data/validation/` convention. The shared launcher was inspected but not modified.

## Time budget

| Boundary | Seconds |
| --- | ---: |
| Agent development | 7,200 |
| One final build | 3,600 |
| Each service load / warmup | 120 / 30 |
| Each query attempt | 0.050 |
| Primary supervisor | 66,000 |
| Single audit session / wrapper | 1,100 / 1,200 |
| Finalization | 30 |
| Outer verifier | 67,800 |

The worst allowed recovery path is `3600 + 5 * 76 * (120 + 30 + 0.05) = 60619` seconds of candidate work. Another `(5 * 76 + 1) * 11 = 4191` seconds covers process/IPC cleanup, leaving 1,190 seconds in the primary supervisor for setup and scoring. The outer limit leaves 525 seconds beyond the primary, audit, finalizer and their 45 seconds of termination grace. Candidate phase deadlines have not increased. Initial load/warmup failure in any pass is a whole-task failure; a failed recovery load/warmup invalidates the affected attempt.

## Completed checks

- Named host-safe unit suite: 38 tests passed (`test_development`, `test_scoring`, `test_ipc_cleanup`, `test_integrity_gate`, `test_api_access`, `test_repetition`, `test_budget`).
- Disposable verifier container: 59 tests collected, 51 passed and 8 skipped. Six storage tests needed prepared mounts and passed separately; the two checks needing source-tree metadata/public tools were covered by the host suite. The container tests exercised real worker isolation, process cleanup and the real UID/Landlock audit restrictions, with 2 CPUs, 4 GiB RAM, no swap, private IPC and no external network.
- All six prepared-storage tests passed: physical ENOSPC, the exact 34 MiB artifact boundary, oversized artifacts, hardlinks, symlink rejection, read-only serving index and inaccessible build scratch.
- Public helper passed three disposable-container fixtures: normal responses scored 100, repeated timeout recovery scored 80, and malformed-response recovery scored 80. Each ran 25 query attempts; the normal fixture loaded five services, and each recovery fixture loaded ten. Fixtures asserted one build, fresh runtime state and automatic score sorting.
- The actual `test.sh` entrypoint, grader, isolated audit wrapper and finalizer passed the seven offline cases below. Every case invoked the compliance audit exactly once.
- Both agent and verifier Docker images built successfully. The container smoke tests copied the current verifier files into their disposable container; they did not depend on a previously built image's test-source snapshot.
- Both Compose overlays parsed successfully with `FORMULA_CPUSET=2,3`. The standard launcher's selection was separately tested against mocked available CPUs `{2, 3}`.
- `python -B scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval --merge-ready`: 0 errors. Python AST, TOML, shell syntax and scoped `git diff --check` also passed. The six asset records match their original source/size/hash fields. The three restored small files (`corpus.json`, validation queries and validation judgments) passed size/hash checks. Hidden inputs, `source-manifest.json`, and both copies of `scoring.py` retain their original hashes.

| Offline entrypoint case | Numerical reward | Final reward | Exit status |
| --- | ---: | ---: | ---: |
| Valid submission, accepted audit | 1 | 1 | 0 |
| One query times out in two of five passes | 1 | 1 | 0 |
| One query times out in three of five passes | 75/76 | 75/76 | 0 |
| Audit rejects | 1 | 0 | 0 |
| Audit decisions disagree | 1 | 0 | 1 |
| Audit details are missing | 1 | 0 | 1 |
| Build fails | 0 | 0 | 0 |

Local evidence is under `/tmp/bingyu-formula-fixes-20261105-6kgm1jz_/`: `container-unit.log`, `public-container/public-smoke-results.json`, `end-to-end/*/summary.json`, `end-to-end/storage-tests.log`, both image build logs and `final-contract-checks.json`. Host unit tests used the existing `jianlv_workspace/envs/search_swe_cpu` Python environment; bytecode writes were disabled.

Naming follow-up: the audit directory is now `tests/jailbreak_judge/`. Docker installation paths, runtime configuration paths, RewardKit result-group lookup and existing tests were updated together. After the rename, `python -B -m unittest test_integrity_gate test_budget -v` passed all 13 tests, including real RewardKit configuration discovery; shell syntax and stale-reference checks also passed. Audit criteria and scoring behavior are unchanged. The image builds and full container checks above precede this naming-only follow-up.

## Scope of the evidence

The entrypoint fixtures used 76 synthetic queries and a tiny artificial corpus; their scores test control flow, not retrieval quality. To avoid modifying shared host mounts, disposable storage fixtures used private bounded tmpfs mounts and replaced only the production FUSE mount-type precondition inside the disposable container. Physical capacity, ownership, copying and accounting checks still ran. The production FUSE-backed layout was not changed or freshly exercised through the standard launcher.

The offline audit stub replaced both pinned backend copies only inside disposable containers, preserving the real wrapper's hash check, user switch and filesystem restrictions. No live model request was made. A trusted test wrapper introduced the synthetic timing failures. An earlier public-helper probe in the shared host PID namespace exceeded 50 ms because process discovery scanned the host process tree; the reported timing checks therefore use private PID containers, as task execution does.

The large corpus assets were not restored locally for this revision. No full-corpus build, coding-agent trial, live API/LLM audit, or new benchmark score was produced. Existing HF revision `3635ca4269c1a1122c2da50187d0db42f3f73006` remains the source for all six assets. A new host still needs the documented FUSE/Landlock prerequisites and performance validation.

## Current source hashes

Original structured-source SHA-256: `9e35c22f7cf4dedcb1ea3ad8c6b8640c4f25fe1f41e21b8c63736b04d88bf174`.

| File | SHA-256 |
| --- | --- |
| `instruction.md` | `25485bace236922e95d025cc4419e7a8df903c4e669a9c5b3cfd3502f9488f8c` |
| `raw-instruction.md` | `ba835c667caf6220248380d919f85792e4b53f1e7a372324f0f880b25aa38558` |
| `task.toml` | `42020cdf257ced347c9ef93385a6d64167dd5ab757479adc7264019766667fad` |
| `assets.json` | `f7e5a9f1d0c0c8474734229fb6e560f80c5cb33ee394ed53241ecda955cbae10` |
| `tests/grader.py` | `b3bc8a204c16c7f0cfd847a20d6f5695eb27e9b5ea437af3832978bc804019eb` |
| `tests/integrity_gate.py` | `2be6cb8ce0085d234d32624b61083019709b487bd2558bcbd3ad8c8e349a52ba` |
| `tests/test.sh` | `f62e93e4f4fc9d8f8954fa5fd2036ae52f93f2dada8c790c425686de1827c3fc` |
| `tests/repetition.py` | `ed26f3b769956f014f5926a5b59f9f4b29dd155c55a0dd47cb4e93ad5bbebe1e` |
| `environment/tools/check_submission.py` | `cbe38fa2c3408eea1c8f1aa933202bbacc3820d15d63d2d9ca4e16965fd53bbd` |

# API access revision validation

Date: 2026-11-03. Base commit: `c7f8a8064e0ff1be30bca3bf4b42ab6b18e60b03`.

The task still measures formula retrieval quality over the existing corpus and 76 hidden queries. Development and the timed final build may now use the OpenRouter/Jina APIs described in `environment/docs/available_resources.md`; model-weight downloads are prohibited. Loading, warmup and queries remain offline. The user-provided `available_resources.md` was preserved byte for byte.

The reference was `tasks/agentic-search/task.toml` and `tasks/agentic-search/tests/run_submission.py`: reuse the two API hosts, submission credential names and separation from judge credentials. Keep this task's resource limits and restrict API credentials/network access to the build worker in verification.

## Preserved contract

The task retains 2 CPUs, 4 GiB RAM, 64 GiB total storage, no GPU, 7,200 seconds for development, 3,600 seconds for building, 120 seconds for loading, 30 seconds for warmup, 50 milliseconds per query, a 34 MiB prepared-artifact limit and a 40 MiB serving filesystem. Numeric scoring, data assets, storage enforcement, development OOM enforcement and Compose definitions were unchanged.

The initial API-access implementation updated instruction paragraphs 4, 5 and 14 for API permissions, time accounting and credential separation, preserving other paragraphs at that stage. The contributor subsequently rewrote and shortened the instruction. The structured source retains the full policy; the agent-facing instruction remains one source line per paragraph.

Initial API-change instruction SHA-256: `000bd80fb6420efddaa57bef6d9b872821ffe06832a5ce4e185c312129c3b8ad`.

Structured-source SHA-256: `9e35c22f7cf4dedcb1ea3ad8c6b8640c4f25fe1f41e21b8c63736b04d88bf174`.

## Completed checks

- `python scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval`: 0 errors.
- Harbor `TaskConfig.model_validate_toml` and `scripts.egress.config.validate_task_networks`: passed; all task phases declare only `openrouter.ai` and `api.jina.ai` for submission egress.
- From `tests/`, `python -m unittest test_development test_scoring test_ipc_cleanup test_integrity_gate test_api_access -v`: 27 tests passed.
- Disposable Docker container, using the existing `large-scale-formula-retrieval__hz7xygu__verifier__trial-main:latest` image with the current test files copied in: `python -m unittest test_api_access test_runtime -v`, 16 tests passed. The container used 2 CPUs, 4 GiB RAM with no swap, private IPC and `--network none`; the connectivity fixture used loopback only.
- The container checks cover build-only submission credentials and socket access, continued offline serving, hidden-file/reward protection, process cleanup, memory/storage enforcement and timeouts. Dummy credentials were used; judge/coding-agent credentials were excluded from both workers.
- Python syntax, shell syntax, unchanged-budget/resource checks and `git diff --check`: passed.

## Remaining evidence

No live provider request, full-corpus API-assisted build, fresh coding-model evaluation or integrity-model API call was performed for this revision. The container tests validate the worker boundary, not provider availability or a complete Harbor run. Existing model scores belong to the previous resource policy and do not validate the API-enabled setting. See the README's dated checks for historical evidence.

## PR preparation — 2026-11-04

Current instruction SHA-256: `ccb47bcc1b7c813ee2c6814bd7b119cbeb51dda071c17b182c13b34f9d8a57aa`. The current task package passed the static checker with 0 errors. The runtime tests above precede the final prose rewrite; a fresh coding-agent/verifier run remains pending.

## Harness log transport — 2026-11-07

Development logs now use a harness-independent directory on the existing
quota-backed filesystem. A trusted finalizer stops remaining solver processes,
snapshots regular log files and private memory evidence, then lets Harbor
convert and transfer the ATIF artifact to the independent verifier. The solver
cannot write to the archival directory after finalization. Pi's integrated and
native routes share the Search-SWE ATIF converter.

Completed checks:

- `tests/integration/bounded_logs.py`: Codex, Claude Code, Pi (integrated and
  native), Antigravity CLI and Gemini CLI passed their real Harbor run,
  conversion, artifact-transfer and independent-verifier lifecycle with
  synthetic CLI executables. The small ext4/FUSE fixture uses a 64 MiB
  development filesystem and the task's existing 40 MiB serving filesystem.
  Each case confirmed ENOSPC for oversized logs, protected private evidence,
  preserved trusted host metadata and rejection of unsafe log links/FIFOs.
  The verifier ran the task's actual trajectory-protection and development
  evidence checks. No coding-model or judge API requests were made.
- In the cached task verifier image, with network disabled, 2 CPUs and 4 GiB
  RAM: `python -m unittest test_development test_scoring test_ipc_cleanup
  test_integrity_gate` passed all 26 tests.
- `python scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval`:
  0 errors. `python scripts/validation/check_release.py`: 0 errors, 0 warnings.
- `python -m unittest discover -s tests/unit`: all 400 repository tests passed,
  including bounded log transport, safe snapshots, stopping background writers,
  ATIF provenance and both Pi routes.

Task instructions, resource limits, inputs and scoring/verifier code are
unchanged by this infrastructure repair. These checks establish harness log
compatibility; they do not constitute a full-corpus run or a new model score.
Historical trajectories and benchmark results were not modified.

## Follow-up review fixes — 2026-11-07

Archive preflight charges each regular path's expanded size, including sparse
holes, repeated hardlinks, allocated blocks and directory/file metadata. The
container snapshot and host merge use the existing 512 MiB diagnostic reserve
as their archival safety budget. Finalization runs after harness export and
fails the agent phase before Harbor's best-effort log download can hide an
error. Host-generated trajectories are checked both at run completion and after
post-run conversion. Source logs are retained on failure.

Antigravity collection compares file identities and content fingerprints from
before and after the run, including SQLite WAL updates and legacy JSON/JSONL
sessions. Unchanged old sessions are excluded independently of their timestamps.
Harbor still performs the native-event-to-ATIF conversion.

Completed checks:

- Full repository suite: 417 tests passed. All 60 targeted log, Antigravity,
  Pi and native-agent regressions also passed. Cases include sparse-file and hardlink
  expansion, metadata overhead, same-size/same-timestamp content updates,
  replacement inodes, old-session exclusion, legacy sessions and SQLite WALs.
- Docker/FUSE negative fixture: a 1 GiB sparse log with zero allocated data
  blocks was rejected before expansion. The original file remained in run
  storage, the trial recorded an infrastructure exception, and the independent
  verifier did not start. Command: `python tests/integration/bounded_logs.py
  --output <fresh-directory> --tools-cache <verified-cache> --agents codex
  --archive-failure`.
- All six Docker/Harbor success routes passed again: Codex, Claude Code, Pi
  integrated/native, Antigravity and Gemini. The Antigravity transcript and run
  marker were forced to have identical nanosecond timestamp values, with no
  sleep workaround. Its real Harbor converter produced ATIF and the independent
  verifier accepted the protected trace and private development evidence.
- Task static check: 0 errors. Repository release check: 0 errors, 0 warnings.

The task's instructions, numerical/resource settings, scoring code and assets
are unchanged. No model/judge API calls or benchmark-result updates were made.
