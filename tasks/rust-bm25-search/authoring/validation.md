# Validation record

This submission is supported by full author-implementation runs, a completed
Harbor Oracle trial and an independent GPT-5.6 Sol / max coding trial through
Codex collaboration. The independent candidate completed the full verifier but
scored zero because its MRR was slightly below the exact reference floor.
Harbor's Codex API route remains untested after an exhausted-credit preflight;
the hosted collaboration trial is documented separately below. Official asset
pins are still needed before the task can pass the merge-ready check.

The contribution branch is `add-rust-bm25-search`, based on
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8`. The contributor is
MXueguang (`x93ma@edu.uwaterloo.ca`). A design summary was recorded before scaffolding
in ignored `jobs/rust-bm25-search-authoring/design-before-scaffold.json`.

## Full reference

The pinned corpus passed SHA-256 verification and a full count/unique-ID audit.
All 8,841,823 IDs are present. Dev contains 6,980 queries; the 54 public DL20
warmup queries have no ID or normalized-text overlap with dev. All dev queries
have positive judgments. Only passage text was indexed.

Pyserini 1.4.0 with k1=0.9, b=0.4 achieved MRR@10
`3236243/17589600 = 0.18398616227770956`. On this host under a 4-CPU, 16-GiB
container limit, indexing took 88.891 seconds and produced 660,057,576 bytes.
The full warm dev batch took 28.029 seconds (249.029 sequential queries/s).
Five new-process startup samples had median 6.175 seconds; they include
Python/JVM and optional-module import overhead, and do not evict OS file cache.
Sampled peak process RSS was 1,379,392 KiB. These are observations, not stable
machine-independent latency or memory guarantees.

Initial reference import failed because a Pyserini optional module constructed
an OpenAI client without a key. A documented non-secret constructor sentinel
fixed that local-only import; no service was contacted. The fresh retry then
completed all queries. Full metadata is in `reference-observation.json`.

## Local checks

Metric/protocol tests cover exact quality comparison, full query denominator,
multiple relevant hits, rank 10, malformed/duplicate/nonfinite output,
timeouts, process cleanup, overlap, cold/warm inconsistency and index links.
Both Docker contexts build with pinned Rust and an offline dependency lock.
The container isolation probe checks that submitted code cannot read hidden
qrels, change rewards, read raw corpus or an outside cache during search,
truncate the immutable index, or create a persistent cache during search.

The probe exposed a missing execute grant for the ELF interpreter; that was
fixed explicitly and both index/search probes now pass. Landlock ABI 1 is
available on this host. Compilation uses Unix privilege separation rather
than Landlock, since ABI 1 forbids the cross-directory renames Rustc needs.
Search uses both root-owned read-only artifacts and Landlock confinement.

## Commands and outcomes

- `python -m unittest discover -s tasks/rust-bm25-search/authoring -p 'test_*.py'`:
  17 tests passed. Added regressions include a full stdin pipe, a descendant
  retaining stdout, huge numeric output, and a compiler temporary file that
  disappears while workspace usage is measured. A non-table Cargo `package`
  value is also rejected as an invalid submission rather than an infrastructure
  error; that case passed in a fresh final-image container with reward zero.
- `.venv/bin/python -m unittest discover -s tests/unit -p 'test_*.py'`:
  171 discovered, 169 passed, 2 skipped because host `harbor-rewardkit==0.2.0`
  is absent. Those two tests concern other tasks' model-judge backend; this
  task has no judge dependency. No failing test was disabled.
- `.venv/bin/python scripts/validation/check_tasks.py tasks/rust-bm25-search`: zero errors.
  `.venv/bin/python scripts/validation/check_release.py`: zero errors and warnings.
- Asset downloader `--verify-only`: both files verified against pinned hashes.
  Both Compose overlays rendered against a temporary base service; shell
  syntax, Python compilation and `git diff --check` passed.
- Both Docker images built using `sudo -n docker` on this host. Agent CLI
  versions were checked inside the final image: Rust 1.85.1, Codex 0.157.1,
  Pi 0.87.1, Claude Code 2.1.283. The agent image contained no verifier qrels,
  reference worker or hidden dev queries. The public synthetic test passed
  with the privately authored Rust binary.
- `authoring/check_negative_containers.py --sudo --output .../negative-final`:
  missing source, a failing index command and malformed search output each
  produced `invalid_submission` with reward 0 in a new separate container.
  Timeout and process-cleanup cases were exercised by the protocol tests.
- `authoring/check_isolation.py` inside a disposable verifier: passed indexing
  and search access checks, including unchanged reward and denied hidden data,
  raw-corpus search access, outside cache reads, index truncation and cache writes.
- Merge-ready checker with base `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`:
  four expected errors, requiring both data entries to use the official
  `search-swe/Search-SWE` repository and `tasks/rust-bm25-search/` prefix.
  Development pins remain real immutable Tevatron commits; no official SHA
  has been fabricated to hide the publication prerequisite.

Repository integration required adding the new offline task to the explicit
network inventory, documenting that it requires no trajectory-judge credential,
and installing the repository's pinned agent CLIs. The first repository test
run caught those omissions; the rerun passed with the complete integration.

The first full author trial built the entire Rust index but failed at startup
because of the verifier's missing ELF-interpreter grant. Its zero was an
infrastructure defect, not a retrieval-quality failure. After that fix, the
next full trial passed with MRR `0.18729482194023742`, score `0.377625401141`,
696,567,340 index bytes, 310.285 seconds to build, 112.697 seconds for dev,
61.936 sequential queries/s, cold median 0.429 seconds and peak process RSS
793,632 KiB. Its fresh local reference reproduced the exact pinned MRR.
The score below 0.5 is expected: this simple self-built implementation is
slower on warm queries despite meeting the quality floor.

The final repeat uses the hardened request/EOF controller. A later workspace
monitor fix only tolerates compiler temporary files disappearing during its
directory walk; the specific regression and a fresh compile/command-failure
container passed. It changes neither retrieval, measurement nor scoring.
The full repeat's image fingerprint and any post-run source difference are
recorded separately from the final image. Those author measurements are distinct
from the later independent model trial below.

The repeat completed successfully: MRR `0.18729482194023742`, reward
`0.376796488284`, 696,567,340 index bytes, 308.297 seconds to build, 112.046
seconds for the full dev batch (62.296 sequential queries/s), cold median
0.431 seconds and sampled peak search-process RSS 790,120 KiB. Its entire
6,980-response file has the same SHA-256 as the preceding full run:
`c8483498457948202f20419ac78dd9fb18933a741803efc94c66cc00ef06baab`.
The two warm batch times differed by about 0.58%. This is limited evidence
from one host, not a cross-machine reliability study.

[known-good-observation.json](known-good-observation.json) includes the full
metrics, same-run reference, source/image hashes and the narrowly scoped
post-run monitor fix. The evaluated instruction SHA-256 is
`9f566cfdd7465d093da2c619a0d2ad6936ad39dcdbad0a630193b52328de8b62`;
the author trial tests its interface with prepared source, not a model reading
that instruction. Full local logs remain in ignored
`jobs/rust-bm25-search-authoring/author-final-03` and negative-case directories.
The author Rust source/index are also ignored and are not in the agent image
or a public solution directory. Completed author containers were removed after
preserving their relevant artifacts and logs.

## Validation scope and merge follow-up

The independent hosted-model trial below complements the author and Oracle
evidence. Its deterministic measurement is valid even though it fails the
quality gate. Maintainers should review the remaining harness coverage: it did
not exercise Harbor invoking the pinned Codex CLI, and full provider trajectory
and token/billing data were not exported. Input redistribution review, official
dataset publication and immutable official HF pins remain outstanding before
merge-ready validation.

At initial submission, the launcher dry-run stopped with
`Set --model or AGENT_MODEL`; no coding-model trial had run. The later explicit
request selected GPT-5.6 Sol. A minimal direct OpenAI Responses probe using that
model and `max` returned HTTP 429, `credit_balance_exhausted`, before any Harbor
trial started. The requested model was then run through the session's hosted
collaboration capability. This task's deterministic verifier needs no judge key.

## Harbor integration follow-up

An ignored private task snapshot under
`jobs/rust-bm25-search-authoring/harbor-integration/rust-bm25-search` adds an
Oracle `solution/` containing only the existing author source. No solution was
added to the public package or agent image. Harbor 0.22.0 compiled that source
offline, passed the public synthetic check, and collected exactly `Cargo.toml`,
`Cargo.lock` and `src/main.rs`; all three collected files match their input hashes.

The first integration attempt stopped before starting a task container because
the local sudo Docker wrapper discarded Compose infrastructure variables. The
job-scoped wrapper now preserves only those named non-secret variables; no host
Docker permissions or network settings were changed. The second attempt found
an actual task integration defect: Docker rejects explicit `hostname` and
`extra_hosts` when Harbor shares its egress-control sidecar's network namespace.
Those Compose options were removed. The verifier startup now ensures its
inherited hostname has a local `/etc/hosts` entry when needed. Prompt, quality
floor, scoring and resource limits are unchanged.

The third integration attempt completed successfully: one total/completed trial,
zero errored/running/pending trials, no trial exception, verifier status `ok`,
quality gate passed, and Harbor reward `0.379283503451`. Docker inspection
confirmed 4 CPUs, 17,179,869,184 bytes of memory and memory-plus-swap, 256 PIDs,
and Harbor's separate restricted network namespace. Its runtime source snapshot
and initial failed-attempt diagnoses are retained in the ignored run directory.
This is an Oracle integration check, not the required configured coding-model
trial.

The exact launch arguments, with the checkout-relative executable and paths,
were:

```bash
.venv/bin/harbor run \
  --path jobs/rust-bm25-search-authoring/harbor-integration/rust-bm25-search \
  --agent oracle --env docker --force-build --yes \
  --n-concurrent 1 --n-attempts 1 --max-retries 0 --job-name oracle-03 \
  --jobs-dir jobs/rust-bm25-search-authoring/harbor-integration/runs
```

The process used the job-local sudo Docker wrapper described above. Use a fresh
job name when reproducing. The author source is private and is not restored by
downloading the public task assets.

Candidate MRR is again `0.18729482194023742`; all 6,980 responses match both
previous manual runs byte-for-byte. Compilation took 19.272 seconds, indexing
307.627 seconds, and the index contains 696,567,340 logical bytes. Warm search
took 111.092 seconds (62.831 sequential queries/s), cold median was 0.439 seconds,
and sampled peak search-process RSS was 790,820 KiB. The same-run reference
reproduced exact MRR `3236243/17589600`, took 26.271 seconds for warm search and
occupied 660,157,062 bytes. Complete measurements, terminal state, image/source
hashes and artifact fidelity are in [harbor-observation.json](harbor-observation.json).

During that run, a separate malformed-manifest probe exposed an `AttributeError`
for `package = []`. The final grader checks the table type explicitly. The new
regression covers arrays, strings, booleans and integers, and
`check_negative_containers.py --sudo --case malformed-manifest` passed in a fresh
container. The only runtime-source difference from the full Harbor snapshot is
this rejection guard; valid candidate execution and measurement are unchanged.

An anonymous read-only publication preflight downloaded only official metadata
at `6713b1eb7474e0768e906a0151c76af92f0cfcdd` and found no collision with the two
proposed task paths among 335 existing asset records. That existing SHA does not
contain this task's assets and is not used as their source pin. No upload was
made. The upstream terms were checked and recorded in [SOURCES.md](SOURCES.md);
maintainer review and publication remain outstanding.

## Independent GPT-5.6 Sol trial

One independent `gpt-5.6-sol` / `max` agent completed this task through Codex
collaboration with `fork_turns="none"`. It received the original instruction in
a clean task-image container with four CPUs, 16 GiB memory, 256 PIDs, no network
and read-only public data/docs. It received no conversation history, author
solution, hidden queries/judgments or previous trajectories. Parent messages
only requested progress reports. The evaluated task commit is
`ae5a6f6c10283559953dfe90270b5ff659b88477`; the instruction hash remains
`9f566cfdd7465d093da2c619a0d2ad6936ad39dcdbad0a630193b52328de8b62`.

After the agent finished, exactly `Cargo.toml`, `Cargo.lock` and `src/main.rs`
were collected and frozen. The Cargo files match the starter. Source review
confirmed native Rust indexing, persistence, BM25 scoring and retrieval, with
no existing retrieval-engine calls, answer tables or evaluation detection
observed. The agent used the shared CPU image's Pyserini installation for
development comparisons on public passages/queries and a synthetic corpus;
that library is not used by its submitted implementation. Its document IDs
are reconstructed from row order, an assumption specific to this fixed input;
this run does not establish correctness for a shuffled corpus.

The agent container was stopped before a fresh separate verifier recompiled
the source, rebuilt all 8,841,823 passages, checked all 6,980 dev responses and
cold/warm consistency, and rebuilt/measured the pinned Pyserini reference.
Candidate execution used UID 10001 and the existing Landlock restrictions.
The verifier finished with exit code 0 and status `quality_below_reference`.
There were no unresolved runtime/reference/judge errors; no model judge is
used. This is a valid completed measurement with reward **0**, not an
infrastructure failure.

| Metric | GPT-5.6 Sol submission | Same-run Pyserini reference |
| --- | ---: | ---: |
| MRR@10 | 0.1839805908036567 | 0.18398616227770956 |
| Warm batch seconds | 17.215982 | 26.096032 |
| Sequential queries/s | 405.437 | 267.474 |
| Warm p50 / p95, ms | 1.824 / 6.460 | 2.234 / 11.578 |
| Index bytes | 593,845,613 | 659,074,562 |
| Process-cold median, ms | 45.732 | 6,107.460 |
| Sampled peak search RSS, KiB | 634,356 | 1,444,812 |

The candidate compiled in 19.242 seconds and built its index in 40.762 seconds.
The reference indexing command took 111.222 seconds after a separate
80.668-second corpus conversion. Cold samples include launch and first result
without query warmup; OS file cache is not evicted. RSS covers the search
process, not all container memory. These remain single-host observations.

Candidate MRR is exactly `215743/1172640`, lower than the required reference by
`7/1256400`, approximately `0.00000557147405`. Reciprocal rank is identical on
6,976 queries, better on one and worse on three; 6,792 complete top-10 ID lists
are identical. This comparison does not establish the cause of the ranking
differences. In particular, the quality gap must not be dismissed as timing
noise. The strict gate correctly yields zero despite approximately 52% higher
throughput, 10% fewer index bytes and lower sampled RSS.

This trial shows that an independent agent can implement and execute the full
workflow within the budget, while the exact quality gate remains consequential.
No task instruction, threshold, scoring, resource or runtime changes were made
in response. The single valid result was retained without retrying for a pass.

[model-observation.json](model-observation.json) records complete metrics,
source/image/runtime hashes, model settings, terminal state and limitations.
Source, agent notes, container command events, exact container/verifier launch
arguments and raw deterministic grading logs are retained under ignored
`jobs/evaluations/rust-bm25-search/collaboration/gpt-5.6-sol/max/attempt-01/`.
Full hosted-model trajectory, token usage and billing were not exported; null
cost fields mean unknown. This hosted trial does not validate Harbor's pinned
Codex CLI or its API transport. The existing Oracle evidence covers Harbor's
artifact transfer and separate-verifier integration independently.

## Review fixes: persistent state and disk accounting

The [maintainer review](https://github.com/VectorSpaceLab/Search-SWE/pull/11#issuecomment-6128882684)
identified two valid bypasses at `7d69eba`: System V shared memory survives
process cleanup, and extended-attribute payloads are absent from `st_size`.
Runtime commit `a5ba0d63c70eb159d5aeef820624bde17e19be0b` addresses both.

Every candidate compile/index/search launch now installs an inherited seccomp
filter after dropping privileges. It denies System V IPC, POSIX message queues,
kernel keyrings and xattr operations, including newer xattr syscalls and
io_uring as an indirect access route. The filter checks the syscall architecture,
rejects x32, and kills non-native ABI calls; ordinary Rust threads and file-backed
mmap remain supported. The implementation follows the kernel's
[seccomp filter interface](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
and pinned [x86_64 syscall table](https://github.com/torvalds/linux/blob/v6.13/arch/x86/entry/syscalls/syscall_64.tbl).
A trusted preflight exercises the unprivileged launcher before judging any
submission, so unavailable seccomp invalidates the run as infrastructure failure.

`index_bytes` now rejects all extended attributes on the index root, every
subdirectory and every file. Attribute-inspection errors fail closed. Candidate
xattr syscalls are also blocked because filesystem confinement alone does not
cover metadata reads on outside paths. Both instructions and environment docs
explicitly describe these limits. MRR, reference parameters, reward formula,
inputs, resource budgets and cold/warm definitions are unchanged. The current
instruction SHA-256 is
`da631e4885c5fb7a854a9fb3f107bf2dfd19422b0151fb121ded62751c1b7fef`.

`authoring/check_persistent_state.py` was exercised in two fresh offline
containers. With `--expect-vulnerable` and the old verifier image, it reproduces
4,096 bytes of shared memory left by an exited indexer, accessible by two fresh
UID-10001 search processes after normal grader cleanup and read-only index
locking, while the measured index is one byte. It also reproduces uncounted
xattrs on files, subdirectories and the root after locking. The xattr payload
is 2,048 bytes to fit this host filesystem's metadata limit.

Against the new image, the same fixture verifies blocked IPC creation in all
three phases, denied attachment to a pre-existing segment, inheritance by Rust
threads and fork/exec children, rejection of alternate syscall ABIs and outside
xattr reads, and rejection of all three index-xattr locations. Both fresh search
processes still read the ordinary persisted index. The original hidden-file,
reward, outside-cache and immutable-index isolation probe also passes.

The verifier image is
`sha256:9c13586d8f2e2600dc87abd0c7ef9a64f3c29be687f883679265e2fe8a78bbf8`.
It was rebuilt from the final runtime sources. Task-local tests now total 19,
all passing; repository tests total 171, with 169 passing and two existing
optional RewardKit tests skipped. Review-stage task/release checks and both
Compose configurations pass. Missing source, malformed Cargo manifest, failed
index command and malformed JSON response each produce `invalid_submission`
and reward zero in fresh containers. Merge-ready still reports the same four
official asset repository/path errors, pending separate publication and terms
review.

Two full frozen-source replays then ran sequentially in fresh 4-CPU/16-GiB,
256-PID, network-disabled containers. Each recompiled source, rebuilt all
8,841,823 passages, measured five cold launches and all 6,980 dev queries, then
rebuilt/measured its own Pyserini reference. Both references reproduced the
exact pinned MRR. Both submissions reproduced their prior complete response
files byte-for-byte, including scores.

| Submission | MRR@10 | Reward | Index bytes | Warm seconds | Cold median, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen GPT-5.6 Sol / max | 0.1839805908036567 | 0 | 593,845,613 | 28.677386 | 50.532 |
| Frozen known-good author | 0.18729482194023742 | 0.364022408613 | 696,567,340 | 135.314643 | 451.609 |

The model's same-run reference took 26.409222 warm seconds and occupied
659,967,462 bytes; the author's took 26.300034 seconds and 660,191,460 bytes.
The original model warm speedup was not reproduced in this replay. These are
single-host observations, and the timing differences do not establish a causal
performance effect. Both full runs completed with exit code zero and no
unresolved grading/reference errors. The model's below-floor quality still
earns zero; the unchanged author implementation provides a positive full-run
check of the tightened isolation and disk validation.

[review-fixes-observation.json](review-fixes-observation.json) records complete
reports, final runtime/instruction hashes, source fingerprints, image ID,
regression coverage and comparison with previous outputs. This is grader
revalidation of retained implementations. No new model generation, solver edit,
quality-threshold change or fresh Harbor integration trial occurred. The
original model trial still corresponds to its original instruction hash.

An independent maintainer evidence archive is prepared under ignored
`jobs/rust-bm25-search-authoring/review-fixes-01/maintainer-evidence.tar.gz`.
It includes retained model source, original instruction, agent notes,
progress/completion records, Docker command events, original/final verifier
logs, full results and SHA-256 manifests. It contains no corpus, built index,
author solution, credentials or parent conversation. Delivery to a
maintainer-accessible location remains pending; this local path is not a
shared download link. The full raw hosted-model trajectory was never exported
and is not recoverable from the available command events.
