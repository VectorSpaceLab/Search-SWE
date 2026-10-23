# Runtime and execution

Python 3.12 at `/opt/conda/bin/python`, PyTorch 2.9.0+cu130,
Transformers 5.15.1, PEFT 0.20.0, NumPy, safetensors and CUDA 13.0 are installed.
The development container has 16 CPU cores, 32 GiB RAM and one NVIDIA
A100-SXM4-40GB. The agent phase lasts 7200 seconds including preprocessing,
all training experiments, tuning and public evaluation. There is no separate
training allowance. No additional pretrained models, data or submission APIs
are supplied.

The deployed serving interface is fixed: base tokenizer, labeled query input,
passage-prefixed documents, at most512 tokens and float32 attention-masked mean
pooling followed by L2 normalization. A deployed query uses exactly one complete
E5 forward. The final document tower is the unchanged supplied base; only query
weights may adapt. Submit a standard query LoRA adapter within512KiB (524288 bytes) or use base;
only FP16/BF16/FP32 safetensors are supported. Count every JSON/safetensors byte,
excluding optional Markdown only from this deployment cap. Full checkpoints
remain available for training/teachers within the original32GiB storage budget.
Final submissions contain no custom Python, tokenizer or pooling. Training/development methods remain flexible.
See the task instruction for exact strings, files and limits. The compute contract
applies alongside the1-second query deadline.

All task data, original weights and documentation are read-only under `/task`.
The model is `/task/models/e5-large-v2`.
The public training file is `/task/data/train.jsonl` (1717 records).
Public development groups are `/task/public/dev-groups.json` (20 groups).
The three corpus JSONL files are `/task/corpus/{robust04,core17,news21}.jsonl`;
fields are `_id`, `title`, `text`. Use `(title + ' ' + text).strip()` as document
text. Corpus IDs are unique within a subset. Cross-subset IDs are separate.
All 104 query groups are preserved; 84 remain hidden in the separate verifier.
Two exact repeated topics across Robust04/Core17 are kept on the same side.

Keep training, checkpoints, outputs and caches under `/app`; it has a 28 GiB
writable tmpfs. `/tmp` has a separate 1 GiB tmpfs. Together with fixed model
and input bytes these fit within the 32 GiB task storage allowance. Both tmpfs
mounts consume the same 32 GiB RAM cgroup: writing many checkpoints reduces
RAM available to training. Framework setup, logs and collection staging are
outside task storage; using those paths for training/checkpoints/cache is
prohibited. Only `/app/submission` is collected. The framework temporarily
archives it at `/var/tmp/search-swe-submission.tar`; do not create that archive
or depend on it yourself.

The task instruction defines submission, scoring and failure handling. Public evaluation uses
`/task/runtime/evaluate.py`; it runs the fixed encoding implementation under UID 10001,
read-only weights/runtime, Landlock and seccomp. It requires running as root to
establish that boundary. This is the same encoding/scoring boundary used in
verification; public evaluation cannot read hidden queries or labels.

Task storage is counted by logical file byte sizes, including sparse files.

Reproduce the eligible untrained fixed-format baseline with
`python /task/baselines/baseline.py`. It caches initial-model document vectors
under `/app/baseline-cache`, using the same bf16 model, masked mean pooling,
`passage: ` document prefix,32-document batches and one query per forward.
The query string is exactly `query: {query}\nInstruction: {instruction}`.
This is an optional reproduction tool, not a training requirement or a submitted
cache. Its work counts toward development time/storage. The independent final
verification always re-encodes documents. The fixed relevance floors use a query-text-only E5 comparator.
Submitted queries must still use the required query-plus-instruction format.

Training and validation permissions are defined in available_resources.md.
