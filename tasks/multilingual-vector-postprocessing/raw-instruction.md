# Multilingual Vector Postprocessing

## Task Description

Improve evidence retrieval from the complete mixed-language Belebele/XQuAD candidate pools using a
frozen postprocessing function f(vector, language). Training is optional and no algorithm or starter
is required. Linear/nonlinear/statistical transformations, language-specific parameters, public
development supervision, and unsupervised statistics over the entire candidate pools are allowed.
All learning, language statistics, tuning and submission must finish within the agent phase. No raw
text, encoder weights, alternative pretrained weights, extra data, translation/re-encoding, external
model/data services, hidden labels or reference artifacts may be used. Coding-agent model transport
is separate from submission resources.

## Requirements

Treat /task as read-only. All vectors are raw, unnormalized, 1024-dimensional FP16 mean-pooled
representations from one pinned multilingual-E5-large encoder; input arrays are cast to FP32 for
transform calls. Languages are ar, zh, en, fr, hi, it, ja, pt, ru, es.
/task/data/train/<language>.vectors.npy and matching .ids.npy contain 200,000 rows per language;
/task/data/probe uses the same naming with 20,000 rows per language. IDs are opaque uint64. There
are 2,000,000 training and 200,000 probe vectors in total. Sources and encoding are described in
/task/docs/available_resources.md. Probe and training original-document/identifiable-translation
families are disjoint.

### Transform interface and output contract

Put the complete independent submission, including all weights and dependencies not already in the
runtime, under /app/submission. Use only regular files and directories; symlinks and other
non-regular entries are rejected. Provide transform.py with load(submission_dir: str) returning a
state object and transform(vectors, languages, state) returning an array-like or Torch tensor of the
same shape. vectors is a read-only FP32 NumPy matrix of shape B x 1024 for B in 1..128; languages is
a list of B language codes. Return real, finite FP32-representable values, with nonzero finite L2
norms. The trusted runner casts outputs to FP32, synchronizes its CUDA context and normalizes them.
No query/document ID or phase flag is passed. The exact same frozen function must apply
independently to each vector and language regardless of batch shape, order or other requests.
Repetition/reordering consistency is checked with normalized-vector L2 tolerance 0.01. Parameters
remain frozen during verifier load/transform; loading, compilation, caching and materializing frozen
weights are allowed, learning or estimating new parameters is not. No query-document interaction
reranking is allowed. Use the directory passed to load for local weights; verifier working
directories are temporary and all submitted files are read-only. The public self-check is python
/task/runtime/evaluate.py --submission /app/submission --output /app/dev-check. It evaluates public
development data only.

## Available Validation Data

/task/data/corpus/belebele and /task/data/corpus/xquad each contain documents.jsonl (id/language)
and vectors.npy with corresponding rows: 4,880 documents/10 languages and 1,440 documents/6
languages. Both complete pools are public. /task/data/development/<dataset> contains queries.jsonl
(id/language), vectors.npy and qrels.jsonl (query_id/relevant_doc_ids), with 1,830 and 1,308
queries. Hidden query populations contain 7,170 and 5,832 rows. Original passages, translations and
their questions are grouped before splitting, including detected near duplicates. Hidden queries,
alignment families and qrels are absent from the agent environment. Public IDs/order do not reveal
alignment. Read /task/docs/environment.md, /task/docs/available_resources.md.

## Expected Artifacts

Submit the self-contained `/app/submission` directory, including `transform.py` and all required
frozen parameters and non-preinstalled dependencies. Only that directory and framework-owned audit
artifacts transfer.

## Verification

### Metrics and failure handling

The verifier normalizes outputs, uses FP32 cosine over each complete dataset pool separately, ranks
descending with ascending document ID breaking ties, and retrieves Top-20. Each query has all 10 or
6 aligned cross-language positive passages. Binary nDCG@20 uses the full positive set for IDCG.
Average queries within each language, then languages equally per dataset, then the two datasets
equally to obtain Q. B=0.9127469497437668 and U=0.9353486724891793 give Score = 100 *
clip((Q-B)/(U-B),0,1); the framework reward is Score/100. Configurations for identity, language
centering, global principal-component removal and regularized whitening are selected/frozen using
public development data; B is the maximum hidden Q across those four fixed configurations; U is a
fixed quality reference from the original task calibration, not a theoretical upper bound.
Reusing the baseline is legal and earns zero without improvement. Ideal nDCG=1 is diagnostic,
and extra speed/GPU savings/language count do not earn extra points.

A single query error, timeout, wrong shape, nonfinite or unnormalizable output earns zero for that
query and remains in its language denominator. Document preparation failure/timeout, total resource
violation, use of prohibited data/models/services, continued learning in verification, or violation
of the frozen-function/integrity rules makes the entire task zero. The verifier measures behavior
and time rather than accepting submitted scores. A separate trajectory integrity audit gates the
reward. Raw Q, B/U, per-dataset/language nDCG/Recall, valid query counts and resource/timing
diagnostics are reported.

### Timing and resource protocol

One physical NVIDIA A100 40GB is available in both phases with the same allocation, together with 16
CPUs, 16 GiB memory and 100 GiB total task storage including provided inputs, weights, optimizer
state, checkpoints, indexes and caches. Each container has a combined limit of 512
processes/threads. The whole agent phase is at most 21,600 seconds (six hours), including
reading/coding, all training experiments, statistics, tuning, development checks and final
submission. There is no separate extra training period. The trusted collector stops background work
and freezes /app/submission when the agent ends or its deadline expires. Only that submission and
framework-owned audit artifacts are transferred.

The image is read-only. /app has a 91 GiB tmpfs; /tmp, /root and /var/tmp have 1 GiB tmpfs each,
charged to the same 16 GiB RAM budget. The private /dev/shm area is 1 GiB for IPC and shares that
RAM budget. The small /opt/harbor tmpfs, framework logs and collection metadata are for the
framework, not extra task cache/storage. The submitted verifier process runs without privileged
file/network access and shares the same CPU/RAM/GPU limits. Network/model/data services are
unavailable for task programs. Read the environment documentation for exact installed tools and
writable paths.

Independent verifier preparation is at most 1,800 seconds, including module/parameter loading,
transforming all 6,320 documents and constructing caches. It does not grant further training/tuning
time. Models/documents may be preloaded; warmup uses public queries only. Hidden queries first reach
the transform in the timed phase. Queries are sequential, concurrency one, with at most 0.5 seconds
each for input transfer/transform, GPU synchronization, normalization, full-candidate cosine
scanning, Top-20 selection and output. Labels/metric computation are outside the query operation.
Hanging/exited transforms leave subsequent unanswered queries failed.

## Hidden Test Overview

Held-out queries and qrels remain verifier-only. Passage/translation/question families do not cross
the development/hidden boundary. Each query searches its entire dataset pool, including all positive
translations.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
