# Large-scale Formula Retrieval

## Task Description

Build a formula search engine to locate related mathematical expressions and their original posts.
Input is a LaTeX formula alone; return at most 1000 ranked formula instance IDs with scores.
Maximize human-judged nDCG prime over the complete valid ARQMath v3 collection, not a supplied
candidate list. No required training, architecture or starter.

## Requirements

Optional public models may be downloaded from permitted Hugging Face hosts during development,
pinned to an immutable commit, with repository/revision and file hashes documented in
`/app/submission/README.md`. Include needed weights in the submission, counted against storage.
Final build/query processes have no network or credentials. Use installed libraries/system tools; no
extra packages are downloaded. Formula normalization, structural matching, representation learning,
recall, reranking, lexical retrieval and CPU models are all permitted. Use only supplied corpus/dev
data and pinned public model weights; do not download historical test queries/qrels, precomputed
rankings or additional datasets. No hard-coded query answers, grader access/modification or resource
bypass. The coding agent's model transport grants no submission API access.

### Build interface

The verifier invokes `/app/submission/build.sh --data-dir /task/data/public --index-dir /work/index`
in a fresh environment. It must exit zero within 3600 seconds, including preprocessing, optional
training, compilation, full-corpus encoding, index construction and subprocess work. The index
directory starts empty. `/app/submission` and inputs are read-only. Persistent output goes into the
supplied index directory; temporary files go under `/work/runtime` via `TMPDIR`/`HOME`. Build
descendants are terminated before query serving. No build process is carried over. The verifier
copies only the completed index into an independent 40 MiB serving filesystem, with regular
files/directories only and preserved hardlinks; symbolic links and special files are invalid. It
reserves allocated submission/model bytes there, makes the copied index read-only, and hides `/work`
including all build scratch from the service. Filesystem metadata and 4096 inodes consume some
capacity. Index, submission, models, caches and serving temporary files share this 40 MiB gross cap;
all service writes go under `/serve/runtime`. Accounting uses max(logical size, allocated blocks)
per regular file and counts shared hardlinks once. An index/submission that cannot fit gives overall
zero.

### Load interface

Verifier launches `/app/submission/serve.sh` as UID 10001. Keep it alive; read stdin JSONL, write
one flushed JSON line per request to stdout, diagnostics to stderr. Each response at most 1 MiB, no
unsolicited output. First request:
`{"op":"load","data_dir":"/task/data/public","index_dir":"/serve/index","work_dir":"/serve/runtime"}`.
Reply exactly `{"ok":true}` within 120 seconds, including process startup. Load already-built
data/models; do not perform deferred corpus preprocessing, training, encoding or index construction
during load/warmup. Three public development queries warm up the service within 30 seconds total.
Honor supplied paths in self-tests.

### Query and output contract

Each subsequent request is `{"op":"query","query_id":"opaque-string","latex":"x^2+y^2"}`. Reply
`{"query_id":"opaque-string","results":[{"formula_id":"123","score":0.5}]}` with the matching query
ID and 0–1000 items. Scores must be finite JSON numbers, excluding booleans; formula IDs must be
unsigned decimal strings. The evaluator sorts by decreasing score, ties by output order. Duplicate
instance/visual IDs receive no extra credit; unknown or excluded instance IDs are discarded.
Malformed structure/fields/nonfinite scores/wrong ID/more than 1000 results invalidates that query.
Empty results are valid and earn zero.

## Available Validation Data

`/task/data/public/formulas.tsv` is UTF-8 TSV with CSV quoting and header `formula_id, post_id,
thread_id, type, visual_id, latex`. All IDs are decimal integers; output instance IDs as decimal
strings. Rows retain original official instance and v3 visual IDs. Thread IDs follow the question ID
or answer ParentId in Posts v1.3, correcting stale TSV thread references. Retain all question/answer
instances from 2010–2018, including question titles; exclude comments and official issue flags
containing `d`. `type` is `question`, `answer` or `title`. Inputs are already extracted and
converted.

`/task/data/public/posts.sqlite` has table `posts(post_id INTEGER PRIMARY KEY, thread_id INTEGER,
type TEXT, title TEXT, body TEXT, owner_user_id TEXT, creation_date TEXT)`. Title/body contain
original annotated HTML; read candidates' context freely. `/task/data/public/instance_visual.npy` is
a little-endian int32 array indexed by formula ID, with -1 for excluded/unknown IDs.
`/task/data/public/corpus.json` reports collection counts. All supplied files are read-only.

`/task/data/public/dev/queries.jsonl` has five selected official assessed 2021 queries, each with
string `query_id` and string `latex`; `dev/qrels.tsv` has the complete official 2021 judgments for
those five queries mapped to v3 visual IDs in TREC `query_id 0 visual_id relevance` format. Final
evaluation uses all 76 official assessed 2022 queries and their complete official qrels, isolated at
runtime. Query titles/body are never provided. Neither the remaining historical 2021 queries/labels
nor the public historical test files are authorized inputs.

Use `/opt/conda/bin/python /task/tools/check_submission.py --submission /app/submission --index-dir
/app/dev-index` for a public build/protocol/scoring check. This uses only the five public queries
and reports timing; only the isolated verifier enforces all final resource and failure conditions.
`--skip-build` reuses an existing development index. No algorithmic starter is imposed.

## Expected Artifacts

Develop for at most 7200 seconds. Read `/task/docs/environment.md` and
`/task/docs/available_resources.md`. Only `/app/submission` transfers to the verifier. Put
executable `build.sh` and `serve.sh` there, along with required source and optional pinned public
model weights. Regular files/directories only, no symlinks or special files. Keep development
indexes outside `/app/submission`. Do not submit precomputed corpus indexes, formula embeddings,
answer mappings or corpus-trained parameters that bypass the timed build; regenerate all
corpus-dependent artifacts in the build. Hyperparameters/algorithms may be tuned on the development
set.

## Verification

### Integrity review

The coding trajectory is also transferred to the separate verifier and protected before submission execution. An independent integrity judge reviews that trajectory and the submitted files for prohibited inputs, precomputed test answers, and attempts to bypass the task's resource, timing or grading rules. Legitimate indexes, model parameters and caches derived from allowed inputs within the permitted phases remain valid; low quality, a timeout or an ordinary implementation error alone is not an integrity violation. Final reward is the numerical score defined in this task only when this review succeeds and accepts the submission. A rejected review gives zero; a missing, failed, timed-out or malformed review also gives zero and is reported as an audit infrastructure failure. Only the verifier's judge has its separate API credentials and network access; these are unavailable to submitted programs.

### Metrics and failure handling

For each valid query, sort returned instances, map to visual IDs, deduplicate visuals, remove
unjudged visuals, retain judged grade-0 visuals. Compute nDCG prime using linear gain equal to
official 0–3 relevance and discount `log2(rank+1)`, with IDCG from that query's COMPLETE qrels.
Normalized reward is sum of per-query nDCG prime divided by 76; displayed score is 100 times reward,
in [0,100]. Failures remain in denominator. Build failure/timeout, index/submission exceeding
compact serving capacity, or memory/overall-storage violation makes the whole score zero. Failed
serving cache writes and other query exceptions follow the query-zero/reload policy; the physical
serving cap cannot be exceeded. Faster execution within deadlines gives no additional points. Also
report MAP prime, P prime at 10 (relevance >=2), build/query time, peak memory and index size.
Deterministic relevance metrics; final reward also requires a successful integrity review.

### Timing and resource protocol

Each query has 0.050 seconds (50 ms) end-to-end wall time at concurrency 1. Clock starts before
query transmission and stops after response reception and suspension of all submission processes.
Parsing/encoding, retrieval, context I/O, reranking, query-dependent cache calculations, output and
subprocess work count. Worker family is suspended between phases and queries, preventing untimed
work. Hidden queries are never present during build/load/warmup. Timeout/crash/protocol failure
gives that query zero; the verifier terminates its process family and reloads the built index before
the next query. Remaining unanswered queries also receive zero. Load/warmup failure gives the
affected query zero; initial load/warmup failure leaves all queries unanswered.

2 assigned CPU cores; at most 2 simultaneous CPU execution threads across the process family. 4 GiB
container memory including data, index, model, caches, runtime and descendants; swap disabled. 64
GiB storage including supplied public data, submission/models, indexes, caches, temporary files and
diagnostics; immutable installed software and private verifier inputs are excluded. Both development
and verification use these limits. Bounded writable filesystems enforce actual available capacity,
reserving 512 MiB for logs and 40 MiB for the independent serving volume, plus filesystem metadata;
use `df` for remaining writable space. Writes outside supplied writable directories are forbidden.
No GPU or external model API.

The allocated submission/model files and completed index together must be at most **34 MiB
(35,651,584 bytes)**, counting max(logical size, allocated blocks) per regular file and shared
hardlinks once within each directory tree. This prepared-artifact limit applies before copying and
is checked by both the public helper and final verifier. The separate **40 MiB (41,943,040 bytes)**
physical serving filesystem also holds its metadata, reserved submission bytes, the index, all
caches and serving-time temporary files; leave room for startup and query writes. The artifact limit
reserves headroom rather than assuming the gross filesystem size is usable artifact space. Exceeding
either limit gives overall zero.

After construction, all build processes must exit and all System V shared-memory, message-queue and semaphore objects owned or created by the submission UID are removed and checked for residual state. Changing an IPC owner does not exempt that state. Only the permitted prepared files carry construction results into serving; cleanup or inspection failures prevent scoring.

## Hidden Test Overview

All 76 assessed 2022 queries and complete official qrels are isolated at runtime. Only the five
supplied 2021 queries and their labels are authorized for development; historical test files are not
permitted solver inputs.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
