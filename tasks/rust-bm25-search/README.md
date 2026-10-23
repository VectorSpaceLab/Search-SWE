# Rust BM25 search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `rust-bm25-search` |
| Version | 1.0.0 |
| Authors | MXueguang |
| Primary metric | quality-gated BM25 quality/time/disk tradeoff |
| Compute | 4 CPUs; 16 GiB RAM; 64 GiB storage; 0 GPUs |
| Agent / verifier time limits | 10800 s / 18000 s |

This CPU task asks an agent to implement a complete Rust inverted index and
BM25 searcher from the 8,841,823 raw MS MARCO Passage v1 passages. Generic crates
are allowed; existing search engines and prebuilt indexes are not. A separate
verifier recompiles the source, rebuilds an empty index, and evaluates all
6,980 standard dev queries.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

The system must build an inverted index from millions of raw passages and match a fixed retrieval-quality floor. Query latency and index size also affect the score, requiring coordinated choices in parsing, compression and ranking.

## Verification Explanation

### Scoring and recorded validation

The exact Pyserini
quality floor has been measured, and an independently built author Rust
implementation passed it on all dev queries (MRR@10 0.1872948219). A Harbor
Oracle trial also passed the actual source-artifact transfer and independent
verifier flow. An independent GPT-5.6 Sol / max trial through Codex collaboration
also completed the full verifier: MRR@10 0.1839805908 falls just below the exact
floor, so it earns zero. Frozen model and author sources were revalidated after
review fixes; full outputs match their previous runs. Current timings and
regression evidence are in [review-fixes-observation.json](authoring/review-fixes-observation.json).
The coding trial used a context-free hosted agent with an isolated task container; Harbor's Codex API
route remains untested because the API preflight found exhausted credits.
See
[validation.md](authoring/validation.md) for the evidence and limitations.
Author: MXueguang (`x93ma@edu.uwaterloo.ca`).

The reference is Pyserini 1.4.0, BM25 k1=0.9, b=0.4, default English analysis,
text only. It omits stored raw text, positions and document vectors. Its
MRR@10 is exactly **3236243/17589600 = 0.18398616227770956**. The candidate must
meet this exact floor, rather than a rounded 0.18 or 0.1840.

For valid candidates, quality, hot batch time and index bytes have equal
geometric weights, normalized as `U/(1+U)` with reference-equivalent score 0.5.
Reference timing and disk are remeasured inside each verifier run, rather than
copied from one author's hardware. Five fresh-process startup measurements,
hot p50/p95, sequential QPS, build time and sampled process RSS are also
reported. Cold means a new process with no query warmup, **without evicting the
OS file cache**. QPS is concurrency-one throughput, not server saturation.
RSS is diagnostic process memory, while the container cap includes children
and page cache. These limitations are explicit in both instructions.

Both phases use the shared CPU image, Rust 1.85.1 and the same offline Cargo
lock. Resource envelope: 4 CPUs, 16 GiB memory, 64 GiB workspace, no network or
GPU. Agent budget is 3 hours; compilation 10 minutes, index build 2 hours,
individual requests 120 seconds and each warmup/measured batch 1 hour. These
are engineering budgets to validate with a real model, not universal claims
about hardware performance. The host needs Linux Landlock ABI 1 or newer and
seccomp filters; root-owned files additionally enforce read-only search on older ABIs.

Only `/app/submission` transfers to the verifier. Candidate code runs as UID
10001, separate from root-owned tests, qrels and reward files. Search is
restricted to its immutable index, binary and system libraries. Source-only
recompilation and these controls support the contract; they do not replace
review that the implementation is actually self-built BM25 and contains no
hard-coded answers. No API or model judge is part of deterministic grading.
All candidate phases block persistent IPC, kernel keyrings and extended-attribute
access, including through io_uring. Index files, directories and the root must
have no extended attributes. These checks prevent IPC and xattr payloads from
bypassing the measured index-file bytes.

### Restore and check

From the repository root, with the host dependencies documented by the repo:

```bash
python scripts/download_assets.py --task rust-bm25-search
python scripts/download_assets.py --task rust-bm25-search --verify-only
python -m unittest discover -s tasks/rust-bm25-search/authoring -p 'test_*.py'
python scripts/check_tasks.py tasks/rust-bm25-search
python scripts/check_release.py
docker build -t search-swe-local:rust-bm25-agent tasks/rust-bm25-search/environment
docker build -t search-swe-local:rust-bm25-verifier tasks/rust-bm25-search/tests
docker run --rm --network none --cpus 4 --memory 16g --memory-swap 16g --pids-limit 256 \
  --mount "type=bind,source=$PWD/tasks/rust-bm25-search/authoring/check_persistent_state.py,target=/check.py,readonly" \
  search-swe-local:rust-bm25-verifier python /check.py
```

The data manifest pins existing Tevatron repositories. Hidden queries/qrels are small files in `tests/data`, with
immutable source URLs and fingerprints. Restore them if necessary using
`python tasks/rust-bm25-search/authoring/prepare_queries.py`. Input terms and
toolchain provenance are in [SOURCES.md](authoring/SOURCES.md); the original
MS MARCO/TREC terms apply to the data.

### Reproduce the reference

The author wrappers invoke the same trusted converter and reference code used
by the verifier. Create fresh output paths; these commands refuse to overwrite
existing indexes or measurements. The measured reference is recorded in
[reference-observation.json](authoring/reference-observation.json); its timing
is a local observation, not a portable threshold.

```bash
python tasks/rust-bm25-search/authoring/prepare_corpus.py \
  --corpus tasks/rust-bm25-search/data/corpus.jsonl.gz \
  --output tasks/rust-bm25-search/authoring/output/collection
```

Run these commands inside the pinned verifier image with the task mounted at
`/task-package`, 4 CPUs, 16 GiB memory, no network, and a hostname resolvable
through `/etc/hosts`. No API credential is needed:

```bash
python /task-package/authoring/reference.py build \
  --collection /task-package/authoring/output/collection \
  --index /task-package/authoring/output/reference-index --threads 4
python /task-package/authoring/reference.py measure \
  --index /task-package/authoring/output/reference-index \
  --queries /task-package/tests/data/dev.queries.jsonl \
  --qrels /task-package/tests/data/dev.qrels.tsv \
  --warmup /task-package/data/warmup.jsonl.gz \
  --output /task-package/authoring/output/reference-measurement
```

Pyserini 1.4.0 imports optional encoder modules alongside LuceneSearcher; one
constructs an unused OpenAI client. The reference worker supplies a non-secret
sentinel solely to satisfy that constructor. BM25 makes no API request and
runs with networking disabled. Startup measurements include Python/JVM/module
startup as well as index opening, as required by the process-cold definition.

### Reviewed precedent and instruction audit

The structural precedent is `tasks/sparse-retrieval-pruning`, reviewed on base
commit `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`. Reused patterns: CPU runtime,
explicit source artifact, separate verifier, clean rebuild, unprivileged
candidate and baseline-relative optimization behind a quality gate. Differences:
raw text and complete Rust BM25 indexing, standard passage dev MRR, measured
Pyserini reference, startup measurements and disk in the objective. None of
that task's data IDs, thresholds, resource/API policies or author fields was
copied. This draft deliberately needs no trajectory-judge API.

The structured contract is [raw-instruction.md](raw-instruction.md). The
agent-facing [instruction.md](instruction.md) is a prose rewrite; the mapping
and review boundaries are in [instruction-equivalence.md](authoring/instruction-equivalence.md).
Author candidates, full indexes and trial logs live in ignored local paths;
they are not included in the agent image or a public solution directory.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task rust-bm25-search
bash scripts/run_task.sh --task rust-bm25-search --model YOUR_AGENT_MODEL
```

## References

- [Data, reference implementation and toolchain sources](authoring/SOURCES.md).
