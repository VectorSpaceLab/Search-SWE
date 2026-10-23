# Validation

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

## System V IPC cleanup — 2026-10-23

Task version **0.11.1** addresses PR #27's IPC persistence finding. Once all
submission processes have exited, the verifier enumerates `/proc/sysvipc/shm`,
`msg` and `sem`, removes objects whose owner **or creator** is the dedicated
submission UID using `/usr/bin/ipcrm` as that user, and checks the tables again.
Inspection, removal, timeout or residual-object failures abort retrieval before
another service starts. The existing shutdown path covers build completion,
normal service shutdown, error recovery and index relocation.

- Before the fix, the new real-kernel regression failed in all **12** combinations
  of six boundaries and unchanged/changed ownership: the objects survived.
- After the fix, **22 regression tests passed, 0 skipped**, including real shared
  memory, message queues and semaphore sets. Later sandboxed services cannot
  attach to or inspect the old IDs. Owner-only and creator-only matches are
  removed; unrelated root-owned objects remain intact.
- Injected removal failure, false success with objects still present, timeout,
  unreadable tables and malformed tables all fail closed.
- A real saved Faiss index still gives **50/50** correct responses before and
  after relocation, with both detached children and IPC created at every phase.
- A separate actual-subprocess recovery run creates IPC during build and each
  service load. Timeout, malformed output and early exit still yield **22/25 =
  0.88**, with 50 requests and eight service loads. No IPC reaches the next process.
  Injected cleanup failure after build, during timeout recovery and before
  relocation stops the stage without starting the next process.

Checks ran in disposable containers with private IPC namespaces, two CPU cores,
2 GiB RAM, no network, no GPU and no API credentials, using existing verifier
dependencies. Do not run the UID/IPC cleanup tests on the host. No fresh dependency
install, full-corpus build, coding-model trial or live audit was performed.
The v0.11.0 replay evidence and its timing limitations remain historical.

The instruction SHA-256 remains
`1ac4215f055a528982c01420d85ffff6f683774304e7aa45db19a6d438da5260`.
The structured source, all inputs/labels and asset pins are unchanged; so are
the 25-query denominator, 600-second build limit and 15 ms request deadline.
No HF update is needed. The reviewed base precedent is
`memory-constrained-dense-retrieval/tests/grader.py`'s owner-or-creator IPC
cleanup; this task keeps its existing process/phase orchestration.
Task static and selected-package release checks pass with zero errors or warnings.
Commands, hashes and raw logs are retained outside the package in
`task_development/filtered-ann-retrieval/ipc-cleanup-20261023/`.

## Query split expansion — 2026-10-23

Task version **0.11.0**. The agent-facing instruction is unchanged, SHA-256
`1ac4215f055a528982c01420d85ffff6f683774304e7aa45db19a6d438da5260`. CPU-only, 8 cores, 16 GiB;
600-second build and 15 ms query deadlines are unchanged.

- Public split: five retained plus five relatively easier measured additions,
  **10 total**. Hidden split: five retained plus twenty harder disjoint additions,
  **25 total**. Two of the 27 candidate queries remain unused.
- Each split retains original cases 01–05, covering single/two/three-tag filters.
  Additions are ranked by the reference implementation's median over ten saved
  replays, with maximum latency and source ID as tie breakers; the lowest five
  are public and highest twenty hidden. All additions use broad tag `[23]`.
- All 35 query vectors and IDs are distinct, and the 25 added Top-10 document
  sets are pairwise disjoint. Exact labels preserve the independently computed
  candidate gold; all 35 ID-only gold responses pass the current checker.
- Grader and finalizer now require 25 cases and divide by 25; two service phases
  make 50 requests. **19 regression tests passed with no skips**, including
  final reward 5/25 = 0.2 and rejection of old ten-case evaluation reports.
- A real unprivileged subprocess test with timeout, malformed response and exit
  failures yields **22/25 = 0.88**, with 50 requests and eight service loads.
- Eight runtime assets pass size/SHA-256 verification. The actual downloader
  restores both updated public files from local staging into a temporary directory.
- Five final-split saved-program replays: reference hidden 125/125
  correct and within 15 ms; saved Luna hidden 25/125 within
  15 ms (each round 5/25 = 0.2), and public 25/50
  within 15 ms (each round 5/10 = 0.5). Both return correct answers in every call.
  Reference maximum hidden latency is **14.985 ms**, close to the limit;
  all individual timings are retained, without a guarantee against future host jitter.

These replays reuse the unmodified reference and saved Codex / gpt-6-luna / max
submission from the v0.10.1 run ending in trial
`filtered-ann-retrieval__fvGoMji`. They use the current RPC timer/checker,
five fresh service loads, alternating mount paths, random query order, 8 pinned
CPUs and 16 GiB. Slow replies are recorded with a 5-second diagnostic timeout
and classified against 15 ms. They do not rerun index construction, copy indexes,
execute a new coding agent or run a live trajectory judge. This is raw saved-program
retrieval evidence, not a new full Harbor reward or a measured future Luna score.

The selected-package release check with local unpublished staging has zero errors
and one publication warning. The standard package check reports exactly the two
unpinned public assets. The six corpus/example pins are unchanged; the two new
public validation entries have actual hashes and null revisions with local
`hf-staging` copies. No upload, commit or push was performed. Publishing those
files and pinning their immutable revision remain required for remote restoration.

Commands, selection mapping, before/after snapshots, regression output and all
replay timings are under
`task_development/filtered-ann-retrieval/split-10-public-25-hidden-20261023/`.
The source/rewritten-instruction audit required only the structured source's
hidden-count update; no advice or evaluation implementation details were added
to `instruction.md`. No new scaffold or structural precedent was needed; the
existing package layout, isolation and published resource limits were retained.

## Execution-boundary fixes — 2026-10-22

Task version **0.10.1**. The instruction is unchanged, SHA-256
`8d827124973298a1e1efb3268ed7ae3fa2724c53fcdbde723696e5ac5d8678fc`.
The corpus, labels, ten-query scoring, 600-second build limit and 15 ms request
deadline are unchanged.

The PR #18 review identified three enforceable gaps. The verifier now:

- Kills and checks every live process of the dedicated submission UID after
  build, at service shutdown and before recovery/relocation. This includes
  double-forked `setsid()` descendants and workers whose main thread has exited.
  Failure to finish cleanup invalidates the stage.
- Applies a Landlock filesystem allowlist before executing each service. The
  current index is writable; application code and system runtime files are
  readable. Original corpus paths, their aliases and other work directories
  cannot be read. Root-side corpus maps remain usable; mounted inputs are not
  chmod'ed or chown'ed. Landlock ABI >= 3 is required and failure is fatal.
- Uses `lstat` to accept only an index directory containing regular files and
  directories. It rejects links, FIFOs, sockets and devices before loading an
  index, including at restart and relocation boundaries.

### Executed checks

| Check | Result |
| --- | --- |
| Final grader regression suite | **18 passed, 0 skipped**, including four real container integration tests |
| Detached-process cleanup | Actual double-fork/setsid descendants killed after build, normal shutdown, timeout, malformed output and early exit |
| Exited leader with live worker | Actual detached worker killed even while its thread-group leader reports zombie state |
| Filesystem boundary and reload | Build reads the inputs; both service passes cannot read original aliases, canonical paths, retired paths, a link under the application directory or a `/proc/self/root` alias; real saved Faiss index returns all 20 correct responses after relocation |
| Index file types | Real FIFO, UNIX socket, character device, block device, nested symlink and symlink index root rejected without opening/blocking on them; regular files/directories accepted |
| Existing process negatives | UID, credentials, protected labels/rewards, IPv4/IPv6 block, nonzero exit, missing/malformed output and timeout checks passed |
| Existing partial-credit recovery | Three failed queries yield **0.7**, with 20 requests and eight service loads |
| Task static and selected-package release checks | **0 errors, 0 warnings** |
| Python/shell syntax and changed-file whitespace | Passed |

Tests ran as root inside disposable containers with the dedicated UID 10001;
the cleanup tests must not run on the host. The final suite used eight CPU cores,
2 GiB RAM, no GPU, no network and no API keys. The host reported Linux
`6.8.0-106-generic`, x86-64 and Landlock ABI 4. ARM64 is supported by the wrapper
but was not exercised here.

The initial three-vector integration fixture spent too long starting an
eight-thread Faiss search team. Its service now uses one thread and performs a
warm-up before readiness. No production timeout or thread limit was relaxed.
An attempted offline build from the task Dockerfile missed a dependency-install
cache and was stopped during package retries. Validation instead reused the
existing task verifier's dependencies and built a local image containing the
updated `/tests` tree, using the recorded `Dockerfile.validation`. This is not a
fresh dependency-install build.

### Full-corpus reference run

The existing external reference implementation ran through `test.sh` in a fresh
container: eight CPUs pinned to cores 0–7, 16 GiB RAM, no GPU, no network, no API
keys, and read-only mounts for the original corpus and reference source.

- Build: **210.943 seconds**; persisted `IndexIVFScalarQuantizer`, 10,000,000
  vectors of dimension 192.
- Hidden cases: **10/10**, including all **20** original/relocated requests.
- Maximum request latency: **7.556 ms**; service loads: **2.070 / 2.070 seconds**.
- Raw retrieval: **1.0**; required live audit: **not run**.
- Final reward: **0.0**, `test.sh` exit **1**, due to missing audit credentials.
  The missing-audit gate still fails closed.

This full-corpus run used the initial boundary patch. The final refinement to
recognize zombie leaders with live worker threads was tested afterward in the
18-test suite; that conditional-only cleanup change did not trigger another
full corpus build. The Landlock policy and index validation are identical in
both runs. No coding-model trial, live judge call, asset upload or publication
was performed.

Commands, source hashes and logs are retained outside the task under
`task_development/filtered-ann-retrieval/execution-boundaries-20261022/`.
The full retrieval report is
`reference-full/filtered-ann-retrieval-eval/evaluation.json`; final regression
output is `regression-tests-final.log`. These are local author records, not
claims of publicly accessible evidence.

## Output-contract simplification — 2026-10-18

Task version **0.10.0**, instruction SHA-256
`8d827124973298a1e1efb3268ed7ae3fa2724c53fcdbde723696e5ac5d8678fc`.

- Removed the unused corpus config and its asset-manifest entry. All eight
  remaining assets passed SHA-256 verification; corpus, queries and labels are unchanged.
- Kept the binary-format schema, removed loading code and implementation advice,
  and reviewed the rewritten instruction against the updated structured source.
- Results now require ranked document IDs only. Removed checks on submitted
  distances and their 0.001 error tolerance. Exact squared-L2 ranking, filters,
  result counts, ties, determinism, persistence and latency gates are unchanged.
- Rebuilt the verifier image. All **14 grader regression tests passed**, including
  correct ID-only output, reversed rankings, false reported distances, wrong
  neighbors, timeout isolation, replay checks and the fail-closed audit gate.
- Real subprocess permission/network checks passed. An ID-only service with three
  failed requests scored **0.7**, with all other requests continuing correctly.
- All **20 public/hidden gold ID-only responses** passed validation against the
  original corpus. This checks output acceptance, not retrieval speed or difficulty.
- Static task and selected-package release checks: **0 errors**. No paid API calls
  or GPU use. No new coding-model trial or live trajectory audit was run.

The first small validation container hit its 128-process limit when OpenBLAS
attempted to create 128 threads before tests started. Re-running with
`OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=2` passed. Task resource limits and
submission-process configuration were not changed.

Reports and before/after snapshots are under
`task_development/filtered-ann-retrieval/contract-simplification-20261018/`.
The full index build and latency run below belongs to version 0.9.0; it was not
repeated for this output-only checker change. The build/service orchestration,
input data, exact-neighbor calculation and 15 ms deadline code are unchanged.

## Migration validation — 2026-10-16

Task version: **0.9.0**. Instruction SHA-256:
`34d785fe4ed141b82fcc3acd30490ca87d3f156ce226a485b558869fb0535b0b`.

### Executed checks

| Check | Result |
| --- | --- |
| Task static checker | 0 errors |
| Selected-package release checker | 0 errors, 0 warnings |
| Published asset verification | 9/9 valid sizes and SHA-256; 2.67 GiB total |
| Source equivalence | Corpus/labels unchanged; main grader differs only in its work-directory name |
| Public/private split | 10 + 10 distinct queries; 4 single-, 4 double-, 2 triple-tag filters per split |
| Repository image/network/audit integration | 14 tests, 12 passed and 2 dependency-dependent tests skipped |
| Task grader regression tests in verifier image | 13 passed |
| Real subprocess isolation/negative checks | Passed: UID, hidden-label/reward permissions, credential filtering, IPv4/IPv6 block, exit/missing/malformed output and timeouts |
| Real partial-credit/recovery test | Three failed queries produce 0.7; remaining queries continue; 20 total requests |
| Agent and verifier Docker builds | Passed using current CPU base and repository CLI/audit pins |
| Both Compose overlays | Valid with all source paths present |
| Agent container smoke check | Public inputs available, /app empty, /tests absent |
| Shell/Python syntax and git diff whitespace | Passed |

### Full-corpus reference run

The source author's existing implementation was installed into `/app` in a fresh
verifier container. The reference stayed outside this task. The container used
8 CPUs pinned to CPU cores 0–7, 16 GiB RAM, no GPU, no network and no API keys.
This CPU affinity does not allocate GPUs.

- Fresh build: **195.972 seconds**, below the 600-second limit.
- Faiss index: `IndexIVFScalarQuantizer`, 10,000,000 vectors, 192 dimensions.
- Hidden queries: **10/10 passed**, including all 20 initial/reloaded requests.
- Maximum request latency: **7.239 ms**, below 15 ms.
- Service loads: 2.032 and 2.066 seconds, outside query timing.
- Raw retrieval score: **1.0**.
- Live trajectory audit: **not run**. No model API charges were incurred.
- Final reward: **0.0**, and `test.sh` exited 1 because the required audit had no
  credentials. This confirms the missing-audit gate; it is not a retrieval failure.

Detailed logs, original files, query provenance, file hashes and command records
are under `task_development/filtered-ann-retrieval/migration/` outside the task.
The reference result is in
`reference-full/filtered-ann-retrieval-eval/evaluation.json`.

### Limits of this validation

No configured coding-agent trial or live model audit was run; the user previously
prohibited additional paid API usage. Thus this is a validated migration with a
known-good retrieval run, not a new coding-model difficulty measurement or a
complete audited Harbor trial. The original retrieval thresholds were retained.

The unrestricted repository release checker reports existing unpublished inputs
and ignore-check issues in other unfinished tasks. The selected-package check
for this task has no errors. Official asset publication, final redistribution
review and remote PR name checks were not requested or performed; immutable
personal HF references were preserved. No commit, push or publication occurred.
