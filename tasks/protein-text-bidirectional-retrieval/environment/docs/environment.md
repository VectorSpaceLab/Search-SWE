# Environment

The shared CUDA 13.0/Python 3.12 image supplies PyTorch 2.9.0+cu130,
Transformers 5.15.1, NumPy, SciPy, scikit-learn, FAISS GPU and ordinary build tools.
Task additions are peft 0.20.0 and nvidia-ml-py 13.580.82. The final verifier uses
the same model runtime. Both phases receive exactly one NVIDIA A100-SXM4-40GB,
16 CPU cores, 64 GiB container memory, 100 GiB total task storage and 512 processes.

Development lasts 3,600 seconds total: reading, coding, data processing, all
base encoding, training, tuning, public checks and final submission. Original
inputs and base weights are already downloaded. Work under `/app`; `/tmp` is
also writable. `/app` has a 95 GiB tmpfs ceiling and `/tmp` 1 GiB. Their actual
contents count toward both the 64 GiB memory limit and the 100 GiB total task
storage limit, together with read-only inputs and checkpoints/indexes/caches.
Storage accounting uses logical file sizes, including sparse files.
Container memory plus swap is capped at 64 GiB, with no extra swap allowance.
These ceilings do not promise 96 GiB of simultaneously resident data. Framework
setup, logs and artifact-transfer staging are separate and must not be used for
training, caches or checkpoints.

Read-only inputs are `/task/models/esm2_t30_150M_UR50D`,
`/task/models/BiomedNLP-BiomedBERT-base-uncased-abstract`, `/task/public`,
`/task/docs` and `/task/runtime`. There is no pretrained cross-modal projection,
trained ProtT3/Q-Former checkpoint, feature cache or training starter.

Final code runs as UID 10001 under a filesystem/syscall boundary, with internet
sockets disabled. It can read the supplied models, public data, frozen submission
and system libraries; it can write task files only in its fresh `work_dir`, plus 64 MiB `/dev/shm` for process IPC, cleared after workers stop and counted toward memory/storage. Hidden labels,
other groups' candidates/queries, grader code and rewards are outside that
boundary. CPU/memory/process limits include descendants. Both agent and verifier require one A100 40GB, requested through Compose `count: 1`. See the submission interface below for all query rules.

The final submission is independently limited to 256 KiB (262,144 bytes), counting
all file paths by logical size, including source, dependencies, frozen learned
state and compressed payloads. The unchanged preinstalled bases remain under `/task/models` outside this directory. Every file copied into `/app/submission` counts.
Runtime decoding/dequantization is allowed; new parameter learning is not.


# Encoder interface

The serving system stores one64-dimensional vector per candidate and performs
cosine ranking centrally. This limits the candidate vector table to2,560,000
bytes per10,000-item pool before IDs and metadata. The submission supplies the
protein/text encoder, its local dependencies, and frozen state. Training,
pooling, adapters, hidden-layer widths and internal feature dimensions are
choices for the solver. The vector returned at the boundary has64 dimensions.

Create `/app/submission/encoder.py` with:

```python
class Encoder:
    def __init__(self, *, model_root, checkpoint_root, work_dir):
        ...

    def encode(self, values, modality):
        ...  # N-by64 numeric NumPy-compatible array or Torch tensor
```

`model_root` is `/task/models`; `checkpoint_root` is `/app/submission`.
`values` contains raw strings; `modality` is `protein` or `text`.
All four groups use the same frozen submission. The constructor receives no
dataset, candidate IDs, direction or test labels. No query ID is sent.
The complete submission, including source/dependencies and compressed state,
must contain only regular files/directories and total at most262,144 logical
bytes, counting each path. Unchanged supplied base models are outside this cap.

For each group a fresh isolated candidate encoder receives all10,000 candidate
values in one `encode` call. It may split its internal computation into batches.
It must return10,000 rows in exactly the input order. The scorer validates and
retains those vectors, terminates the candidate process and its descendants,
and removes its work directory and UID-owned shared memory.

A separate fresh query encoder receives one string at a time as a one-element
list and must return shape `(1,64)`. It has no candidate file, candidate vectors,
candidate IDs or candidate-phase cache. Only the trusted scorer holds the
candidate vector table and IDs. Do not transfer test computations between
process phases/groups, precompute unseen queries, cache query representations
or results across calls, batch different queries, or continue background work
after returning. The fresh work directory may contain a trusted CUDA `.nv`
cache from initialization; it contains no prior candidate computation.

Outputs are converted to float32 and must be finite and numeric, with exactly
the required shape. The scorer L2-normalizes vectors, computes their cosine
scores, and returns the20 highest-scoring IDs. Exact score ties are broken by
ascending opaque candidate ID. A zero query vector or query return `None`
abstains and has zero quality. Candidate return `None` is invalid. The scorer
uses float64 accumulation for vector norms to avoid overflow for legal large
float32 values, then stores normalized vectors in float32.


Public self-check: `/opt/conda/bin/python /task/runtime/evaluate.py --root /task/public/valid --output /app/dev-eval`. The task instruction defines time gates and direct reciprocal-top1 scoring.
