# Filtered ANN retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `filtered-ann-retrieval` |
| Version | 1.0.0 |
| Authors | bingyu |
| Primary metric | Mean per-query exact filtered Top-10 correctness and latency |
| Compute | 8 CPUs; 16 GiB RAM; 64 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 5400 s |
| Dataset | NeurIPS 2023 Big-ANN Filter Track / YFCC-10M |
| Public queries | 10 |
| Hidden queries | 25 |

Author: **bingyu**. version: **1.0.0**. Migrated from
`search_swe_bingyu/task-submissions/bingyu/1-x-1` version 0.8.1.

Build a persistent Faiss ANN backend returning exact nearest neighbors subject
to conjunctions of metadata tags. CPU only; no embedding model or retrieval API.

### Data and provenance

The corpus has 10,000,000 192-dimensional uint8 vectors and CSR metadata with
200,386 tag columns. The public split has ten queries (five retained and five
new); the hidden split has 25 queries (five retained and twenty new). All 35
query vectors are distinct. Each split retains two single-tag, two two-tag and
one three-tag case; the additions exercise broad single-tag filtering. A separate
64-document, 17-query example supports functional development without adding
scored cases.

The corpus and small example retain their published official pins. The two updated public validation files are published under `tasks/filtered-ann-retrieval/v0.11.0/data/validation/` at immutable revision `234406eb7e304478e48905829fc0d3233f5a9f1f`. Earlier public files remain available. See [SOURCES.md](SOURCES.md) for attribution and source terms.

```bash
python scripts/download_assets.py --task filtered-ann-retrieval
python scripts/download_assets.py --task filtered-ann-retrieval --verify-only
python scripts/check_tasks.py tasks/filtered-ann-retrieval
```

Runtime `data/` is ignored by Git. The agent receives corpus, public examples and
docs. Hidden queries, labels and the grader are copied into the separate verifier
image. Reference implementations remain outside the task package.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

Filtering changes the eligible neighbor set for each query. Exact filtered Top-10 results must be returned within 15 ms, requiring an index and execution strategy that handle both filter selectivity and vector similarity.

## Verification Explanation

### Interface and scoring

See [instruction.md](instruction.md) and its structured source
[raw-instruction.md](raw-instruction.md).

- `/app/build.sh --vectors PATH --metadata PATH --index-dir PATH`: build a fresh,
  trained Faiss ANN index covering the corpus within 600 seconds.
- `/app/run.sh --index-dir PATH --serve`: load, emit a ready JSON line, and serve
  individual JSON requests over stdin/stdout, each within 15 milliseconds.
- Filters use AND semantics; distance is original-vector squared L2. Results must
  be complete exact Top-10, ordered by `(distance, doc_id)`. Boundary ties count.
  Output contains document IDs; the verifier computes distances independently.
- Each hidden query is checked before and after index relocation. It earns one
  only if both responses are correct, timely and identical. The retrieval score
  is the mean of 25 binary query scores; the two service passes make 50 requests.
- Request failures affect only that query. Protocol failures trigger a restart
  so late replies cannot contaminate later queries. Build, index or service-load
  failures invalidate retrieval. The required trajectory audit gates final
  reward and fails closed when absent or unsuccessful.

Timing includes request transmission and response JSON decoding. Service startup
is outside this timer with no independent timeout; the entire retrieval phase
has a 3,900-second supervisor deadline.

### Runtime and migration

8 CPUs, 16 GiB RAM, 64 GiB storage, no GPU; implementation time 120 minutes.
Both images use `search-swe-base:cpu-py3.12-1.0.0`. Agent and submitted search code
are offline. The verifier permits OpenRouter solely for the root-side audit;
submission processes use UID 10001, a clean environment and a seccomp network block.

At build completion, each service restart and the relocation boundary, the
verifier kills and waits for all live processes of the dedicated submission UID,
including detached sessions and live worker threads with an exited leader.
After those processes exit, it removes System V shared memory, message queues
and semaphore sets owned or created by that UID, then verifies none remain.
Unreadable IPC tables, failed removal or residual objects invalidate retrieval.
Index validation accepts only directories and regular files. Service processes
use a Landlock allowlist for `/app`, the current index and system runtime files;
the original corpus remains inaccessible through canonical paths or aliases.
The root verifier retains its own corpus maps without changing read-only mounts.

The verifier host must support **Landlock ABI 3 or newer** (Linux 6.2+ with
Landlock enabled and its syscalls permitted); the wrapper supports x86-64 and
ARM64. Missing isolation support fails the service load and yields zero reward.
See the [kernel Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html).

Migration updates the task ID, removes obsolete `metadata.task_type`, pins current
agent CLIs and adopts the repository RewardKit 0.2.0 / DeepSeek V4.1 Flash wrapper.
The original audit criteria, exact-ranking score and latency gates are preserved.
Version 0.10.0 removes unused corpus/config.json, strips implementation advice
from visible docs, and requires IDs only instead of returned distances with a
0.001 tolerance. Binary-format documentation retains only the input schema.
Version 0.10.1 enforces the process, corpus-access and regular-file persistence
boundaries above. Version 0.11.0 changes the query split to ten public and 25
hidden cases and updates the scoring denominator. It selects five relatively
easier public and twenty harder hidden cases from 27 repeatedly measured broad
filter candidates, using reference-runtime medians as a difficulty proxy.
The verifier clears and verifies System V IPC at each execution boundary,
using the owner-or-creator cleanup pattern in the reviewed
`memory-constrained-dense-retrieval/tests/grader.py` as a structural precedent.
The instruction, submission interfaces, corpus and time/resource limits are unchanged.
Structural precedents are `memory-constrained-dense-retrieval`
and `sparse-retrieval-pruning` for offline CPU retrieval and protected evaluation.

### Validation

See [VALIDATION.md](VALIDATION.md) for executed checks and unrun layers. Detailed
migration reports live outside the package in
`task_development/filtered-ann-retrieval/migration/`.

The 0.11.0 split has local dataset, grader and saved-program replay checks;
it has not received a fresh coding-model run or live judge call. Reference runs
measure raw retrieval; without the required audit, final reward remains zero.
The public assets are published at the immutable revision recorded above.
The recorded v0.11.1 validation has 22 passing grader regression tests and real subprocess IPC
recovery checks; no fresh coding-model trial or live judge call was run for it.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task filtered-ann-retrieval
bash scripts/run_task.sh --task filtered-ann-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max
```

## References

- [Data, model and method provenance](SOURCES.md).
