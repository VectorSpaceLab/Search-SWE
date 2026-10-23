# GPU environment

The task uses docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0:
Python 3.12, PyTorch 2.9.0+cu130, CUDA 13.0 and the common Search-SWE packages.
Use /opt/conda/bin/python and /opt/conda/bin/pip. Task additions are
rdkit 2024.3.5, duckdb 1.3.2, tensorboard 2.20.0, lightgbm 4.6.0 and
nvidia-ml-py 12.560.30. The agent image includes the repository's pinned
Codex CLI 0.164.0, Claude Code 2.1.309 and Pi 1.4.0. The base supplies Git,
C++ tools and nvcc.

APEX and its GPU top-k extension are built from bundled pinned sources.
The extension targets sm_80 using a fixed CCCL header subset for DeviceTopK.
Original source licenses and commits are retained in vendor/SOURCES.md.
No compiled host environment or author reference solution enters the image.
The host needs the NVIDIA container runtime, cgroup v2, seccomp and Linux
Landlock ABI 3 or newer. The verifier fails closed when these are unavailable.

Both phases request one A100 40GB with Compose `count: 1`, exposed as logical CUDA device
0, 16 CPU cores, 32 GiB total cgroup memory and 64 GiB total task storage.
The memory-plus-swap limit is also 32 GiB; swap does not extend this budget.
Provided public data/models, submission, indexes, tables and caches all count.
Final grading samples logical disk use every 0.5 seconds and at phase
boundaries, including sparse and open-unlinked scratch files. When procfs denies
inspection of a process already marked as exiting by the kernel, a check waits
up to one second for actual exit; a live process that blocks inspection remains
invalid. These checks remain within the applicable wall-clock budgets. /app uses disk;
/dev/shm is a 2 GiB tmpfs whose memory also counts against the 32 GiB cgroup.
The Docker backend does not implement a development filesystem quota; honor
the 64 GiB limit throughout development and keep task files under /app.
Development lasts 21,600 seconds including optional training/tuning. Final
cumulative imports, preparation and loading have 3,600 seconds, with no training
or tuning. Serial requests have a hard two-second complete-response deadline.
See the submission interface below for exact timing and restart behavior.

Read-only inputs are /task/library, /task/models, /task/train and /task/dev;
documentation is /task/docs and public helpers are /task/runtime. The final
verifier mounts target definitions/models and contains runtime/docs; 1M training/development
need not be available then. Future queries, labels and scorer stay outside
submitted code. Only /app/submission transfers. Put missing dependencies there
rather than relying on changes to the agent's global environment.

Final submitted code runs as UID/GID 10001 with Landlock/seccomp restrictions.
It can read its frozen submission, public target definitions, models, installed
runtime and normal system libraries, and write to the supplied scratch and
/dev/shm. TMPDIR and cache variables point to scratch. Verifier data/rewards,
frozen-file writes, other-process inspection, TCP and namespace changes are
blocked. Unix sockets, subprocesses, CPU threads and GPU work are supported.
CUDA may name its own threads through procfs. No extra container capabilities
are requested. For open-unlinked file accounting, the supervisor temporarily
uses the submission's filesystem UID/GID while retaining its root process
identity, then restores both filesystem IDs. Submission processes must remain
inspectable through procfs; disabling dumpability or preventing descriptor
accounting invalidates the submission. Submitted code drops all capabilities
and cannot ptrace the supervisor or read its environment.
Honor supplied paths rather than assuming /tmp is writable. Submission
background processes are cleaned up on query failure and completion.


## Submission interface

Final quality is Recall@10000, averaged equally over configurations within
each target and then the five targets. Reward equals Q (100*Q points).

Write `/app/submission/retriever.py` with these exports:

```python
def prepare(library_dir: str, model_dir: str, index_dir: str) -> None:
    ...

class Searcher:
    def __init__(self, library_dir: str, model_dir: str, index_dir: str):
        ...

    def search(self, query: dict) -> list[int]:
        ...
```

The supervisor calls prepare once and then constructs Searcher. All imports,
preparation and loading share a 3,600-second wall-clock allowance, including
Searcher reloads after failed queries. Preparation is frozen-parameter work:
load, infer, enumerate, compute properties and index; no training or tuning.
Use index_dir and TMPDIR for all writes; submitted files are read-only.
Only `/app/submission` transfers to a fresh verifier. Use regular files and
directories; symlinks and special files are rejected. Dependencies installed
elsewhere do not transfer. The original image packages remain available.

Search is serial in a persistent process. Query shape is
`{"query_id":"q","target":"DRD2","constraints":{"mol_wt":[null,450.0],"logp":[null,3.5]},"k":10000}`.
Targets are DRD2/ESR1/F10/MET/PARP1 and lower docking scores are preferred.
Bounds are inclusive, null is unbounded, and omitted properties are unrestricted.
Properties are mol_wt (Da), logp (RDKit Crippen logP), n_hbd/n_hba (counts),
n_rotatable_bonds (RDKit default strict rotatable-bond count), tpsa (square Å).
Return a Python list of distinct built-in ints; NumPy scalars must be converted
with int or tolist. Return up to k IDs; empty lists are valid. Output order does
not affect set recall. Do not print a separate protocol response: return the
list to the adapter. Ordinary module logging is redirected to stderr.

The target has 12,446,577 combinations. `library.py` preserves the original
CSLDataset ordinal mapping: input reaction order, sorted internal synthon IDs
within each position, last position varying fastest. For example, importing
`Library` from `/task/runtime/library.py` and constructing it with library_dir
provides id_to_name, name_to_id, id_to_smiles, id_to_key and iter_smiles. This
does not contain labels or precomputed properties.

Each two-second timer covers query encoding/delivery, parsing, search, optional
property computation, filtering/reranking, GPU synchronization, serialization,
complete receipt and output parsing/validation. Do not measure only GPU kernel
time. Future queries stay in the supervisor until their turn. Preloading
query-independent predictions/properties/indexes is allowed; query-specific
answer caching is forbidden. After a failure the supervisor kills submission
processes, may reload Searcher with the same index, and keeps the failed query
in the quality denominator. Resource/preparation failures invalidate the task.

Public development uses the original 1M validation candidate membership and
its own library IDs, not target IDs. Its labels are public; 12M target labels
are absent. The public evaluator uses the same submission adapter and timing:

```bash
PYTHONPATH=/task/runtime /opt/conda/bin/python /task/runtime/evaluate.py \
  --library-dir /task/dev/library --private-dir /task/dev \
  --output-dir /app/development-report
```

Public development uses 347,677 original validation candidates and k=279,
rounded from 10000*347677/12446577. Its reward is raw Recall@279, using the same
selection fraction as final Recall@10000. Both use direct Recall as reward.
Use each request k; public IDs belong to the 1M library. Public and target
composition differ, so this is a diagnostic, not a guarantee of final quality.
The evaluator makes the submission read-only for its child; the development
root user may restore write permission to continue editing.

You may derive additional validation constraints, smaller output budgets and
ranking diagnostics using public labels. None changes the final 10,000-slot
budget. No target labels, future test conditions or reference answers are
available for development.

An optional baseline is provided as `/task/runtime/baseline.py`. To use it,
write `from baseline import prepare, Searcher` in your retriever.py. It computes
query-independent full surrogate tables and structural properties from public
inputs, with no training. The default is the public-selected simple-ensemble
family, with choices fixed from public validation. You can implement a different
algorithm or copy/change this code.
A frozen `baseline-index/scores.npy` and `baseline-index/properties.npy` under
your submission may be reused instead of rebuilding; shape must match the
chosen library. All computation and cached assets count against budgets.

An optional submission `baseline-config.json` can specify `{"family":"full-raw"}`.
Families are native, apex-pred, apex-raw, apex-normalized, full-raw,
full-normalized-properties, full-normalized and simple-ensemble. The last family
uses fixed public-validation choices to blend raw/normalized surrogate scores
per target and select a raw/normalized source for each property. Its default
choices are in /task/runtime/baseline-default.json when selected as the baseline.
Build expensive tables during development with
`python /task/runtime/baseline.py --output /app/submission/baseline-index`
to transfer the frozen index and avoid rebuilding it during final preparation.
Building every surrogate/property component can exceed final preparation time;
compute allowed training-independent caches during development and submit them.
The APEX cache/native families
require the target 12M library; full-surrogate families also support the public
1M development library and enforce its candidate membership. Fragment
normalization is a heuristic, not an exact reconstruction of official forms.
No cached predictions or creator reference model are supplied.

The verifier additionally runs an independent trajectory/submission integrity review
using `deepseek/deepseek-v4.1-flash` through OpenRouter. Final reward requires a
successful accepting review. Its credentials and allowlisted API access belong
only to the trusted judge; submitted code retains its existing network restrictions.
The verifier protects a separate trajectory snapshot before running submitted code.
