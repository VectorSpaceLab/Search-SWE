# Protein-text Bidirectional Retrieval

## Task Description

Starting from original ESM-2 150M and BiomedBERT abstracts base weights, learn
protein/text alignment and maximize full-pool bidirectional strict reciprocal top1 pair success
for Swiss-Prot and ProteinKG25. Both directions are required. Use only supplied
models and public train/valid data. Freezing, fine-tuning, adapters, sampling,
pooling, custom alignment and encoder architectures
are allowed. Training is optional; algorithms are not prescribed. Return64-dimensional embeddings
for scorer-controlled cosine ranking; internal features/hidden widths are unrestricted. An official
pair succeeds only when both raw retrieval directions rank each other first. No training
starter/code, pretrained cross-modal head, aligned feature cache, ProtT3 stage-1
weights, Q-Former initialization, extra models/data/teachers or task APIs are supplied.

## Requirements

Use only the supplied bases and public train/valid data. No additional pretrained models, aligned
features, datasets, teachers, external embedding/reranking/generation services or task API
credentials are supplied. Network is disabled for task code; the coding agent's own model transport
is not a task API. All `/task` inputs are read-only. Do not access hidden queries, pair labels,
reference solutions or grader internals, hard-code test answers, train or tune on test inputs,
transfer test computations between groups, or bypass timing, isolation, resource limits or rewards.
Such violations make the entire task zero. Official pairs do not enumerate every biologically
acceptable match; retain the given pairing rather than treating all homologs or synonyms as
positives. Hidden labels and pair feedback are not returned for further development.

### Encoder interface and output contract

Put your self-contained code and any required frozen alignment weights or adapters under
`/app/submission`, including `encoder.py` and any local Python dependencies. Use ordinary files and
directories without symlinks or special files. The entire submission must total at most 256 KiB
(262,144 bytes) of logical file sizes, including source, local dependencies, all learned parameters
and compressed payloads. Count each path separately, including hard links and sparse files; the
preinstalled unchanged bases remain under `/task/models` outside this directory; every file copied
into `/app/submission` counts. Collection, restoration and evaluation reject an oversized submission
with zero score. Runtime decoding or dequantization of submitted frozen state is allowed, within the
existing memory/storage limits; learning parameters during verification remains forbidden. Only
`/app/submission` and the agent trajectory are transferred to the separate verifier; the framework
automatically snapshots those submission contents to `/var/tmp/search-swe-submission.tar` before
transfer and restores them to `/app/submission`, without requiring you to create an archive or
granting extra training time. Unchanged base weights remain available at their supplied paths. In
`encoder.py`, define `Encoder` with keyword arguments `model_root`, `checkpoint_root` and
`work_dir`. The roots are `/task/models` and `/app/submission`. Implement `encode(self, values,
modality)`, taking a list of raw strings and `protein` or `text`, and returning an N-by-64 real
numeric NumPy-compatible array or Torch tensor in input order. Values must remain finite after
conversion to float32. Boolean, complex, nonnumeric, nonfinite or wrong-shape output is invalid. The
constructor receives no dataset, direction, candidate IDs or test labels. The worker runs as UID
10001 with filesystem/syscall restrictions, read-only models, submission and public data; write
inference temporaries only in its fresh `work_dir`. A further 64 MiB `/dev/shm` supports process IPC
and counts toward memory/storage. The work directory may initially contain a trusted CUDA `.nv`
cache.

For each group, a fresh candidate encoder receives all 10,000 raw candidate values in one call;
batch them internally if useful. Its process and descendants exit before a separate fresh query
encoder starts, and its work directory and UID-owned shared memory are removed. Only the privileged
scorer retains the candidate vectors and IDs. The query encoder receives a one-element list for each
raw query, without a query ID, candidate file, candidate vectors, IDs or candidate-phase cache. The
scorer normalizes candidate/query vectors to unit L2 length in float32, using float64 norm
accumulation to avoid overflow, and ranks by exact cosine similarity; equal scores are ordered by
ascending opaque candidate ID. It returns the best 20 IDs. A zero query vector or query return
`None` is a legal abstention and misses; a candidate return `None` is invalid. Candidate-specific
indexing and query–candidate interaction reranking are outside this encoder interface. Do not
transfer candidate/test computations between process phases or groups, batch different queries,
cache query representations/results across requests, precompute unseen queries or continue a request
after returning. The trusted adapter synchronizes GPU work before responding; do not bypass timing
or synchronization. For quality, a pair succeeds only when its description is the first result for
its protein and its protein is the first result for its description; top-20 results remain
diagnostics.

## Available Validation Data

Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. Bases are
`/task/models/esm2_t30_150M_UR50D` and
`/task/models/BiomedNLP-BiomedBERT-base-uncased-abstract`. Train JSONL files
`/task/public/train/{swissprot,proteinkg25}.jsonl` contain `sequence` and `text`.
Original train counts are 430,595 and 422,315. Each public valid directory
`/task/public/valid/<dataset>/` contains the complete original 10,000-record
`protein.jsonl` and `text.jsonl` candidate pools, but `pairs.json` exposes only
10 paired labels per dataset, 20 pairs in total (`p2t`/`t2p` dictionaries).
Public evaluation sends those 10 raw queries in each direction, 40 scored requests total, plus the
three preparation warmups per group,
against full candidate pools. Unlabeled candidate entries are distractors.
This small diagnostic is noisy; you may create holdouts from public training data.
Modality records are `{"id":"opaque-id","value":"raw sequence or description"}`.
Independent modality IDs/orders must be joined by mapping, never row number.
Sequences are at most 1,022 residues (1,024 ESM tokens with specials); raw input
is supplied without a mandated truncation/pooling policy. Do not omit long or
missing records to reduce work. Upstream test is public; runtime hidden isolation
does not establish unseen-family generalization. Duplicate descriptions retain
strict official-pair relevance, not semantic-equivalence judgments.

During development, run `/opt/conda/bin/python /task/runtime/evaluate.py --root /task/public/valid
--output /app/dev-eval` as root. It uses all 10,000 candidates with the 10 labeled raw queries per
direction per dataset, the same isolated two-process protocol, failure handling and timing, and
reports mutual-top1 pair success, directional Acc@1/Recall@20, validity and latency. It freezes
`/app/submission` permissions; restore permissions as root before further edits. Public checks count
toward the development budget and contain no training implementation or hidden feedback. The
`--full` flag is reserved for verifier data containing 10,000 labeled queries per group; it does not
supply hidden labels to the public tool.

## Expected Artifacts

Submit `/app/submission/encoder.py` and all required local dependencies/frozen state. The entire
transferred directory must fit 262,144 logical bytes; unchanged supplied base models remain outside
it.

## Verification

### Metrics and failure handling

For each dataset, let M be the number of official pairs whose two independently executed queries
both rank their paired candidate first, divided by all 10,000 official pairs. A missing, invalid,
failed or late query makes its pair fail; all pairs remain in the denominator. Quality is
`Q=(M_swissprot+M_proteinkg25)/2`, and the score after all gates is `100*Q`. Thus 20 points means
20% of official pairs succeed in both directions, and 100 points means every pair succeeds. Public
checks use the 10 exposed pairs per dataset as their denominators. Individual directional Acc@1 and
Recall@20 are diagnostic. There is no separate speed reward. An independent trajectory integrity
audit must be healthy and accepting; rejection or unavailable audit gives zero. Reports contain
per-dataset mutual-top1 success counts/rates, per-group Recall@20/Acc@1, valid/timeout counts,
latency percentiles, cumulative preparation, resource peaks, raw Q and final score.

### Timing and resource protocol

You have one NVIDIA A100-SXM4-40GB, 16 CPU cores, 16 GiB combined container memory/swap, 100 GiB
total task storage and 512 processes including descendants. The entire development phase lasts 3,600
seconds, including reading, coding, preprocessing, all base encoding and feature caches, every
training/tuning trial, public checks and final submission. Inputs are downloaded before this clock
starts. At the deadline the available submission is frozen; without a valid loadable submission the
score is zero. Development work belongs under `/app` or `/tmp`. `/app` is a 95 GiB tmpfs and `/tmp`
a 1 GiB tmpfs; their actual contents count toward both memory and storage, together with read-only
inputs, bases, checkpoints, indexes and caches. Storage accounting uses logical file sizes,
including sparse files. These ceilings do not promise 96 GiB of resident RAM. Framework setup,
logging and artifact staging are exempt from task storage and cannot be used for task work.

Verification starts each of the four dataset–direction groups independently from the same frozen
submission, with separate candidate and query encoder processes as described above. Only frozen
model files and supplied public assets are shared. Preparation may only load frozen parameters and
perform inference, with no further training, tuning or new alignment-parameter estimation. Each
group has a cumulative 900-second preparation allowance, including imports, both model
initializations, encoding all candidates, scorer vector-table construction, three fixed public query
warmups, process transition cleanup and any recovery preparation. All four preparations together are
at most 3,600 seconds; this is not the total online evaluation deadline. Query-worker recovery
reuses only the scorer-held frozen candidate vector table and starts a fresh query process without
candidate state.

The verifier sends all 10,000 queries in each group serially with concurrency one. Each group
separately requires nearest-rank p95 at most 1 second and has a 3-second hard deadline per query.
The external wall-clock measurement includes sending/parsing the request, tokenization, query
encoding, vector validation, normalization, scorer cosine ranking and sorting, output and GPU
completion. A failed, missing, invalid or over-3-second response contributes zero quality and 3
seconds to latency statistics, with its actual elapsed time also logged. Failed workers are cleaned
before subsequent requests, and their reinitialization consumes the same group's remaining
preparation budget. Every query remains in the 10,000-query denominator; p95 is sorted latency
number `ceil(.95*N)`. Any group's p95 above 1 second makes the whole task zero, as do absent
weights, candidate preparation failure/timeout or resource violations.

## Hidden Test Overview

Each dataset retains 10,000 official test pairs, evaluated in two directions for four 10,000-query
groups total. Hidden labels, candidate-phase state and inter-group state cannot be used by query
encoders.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
