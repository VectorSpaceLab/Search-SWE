# Runtime and hardware

The task uses the shared GPU image `docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` in both phases. Both Compose overlays request one GPU with `count: 1`; the allocated device must be an A10040GB. The verifier discovers its UUID inside the container. Limits are16CPU quota,64GiB RAM, no swap,4GiB shared memory and2048PIDs. CPU-only retrieval is permitted within the assigned container. Model/data/tool mounts are read-only.

Use `/opt/conda/bin/python`, with torch2.9.0+cu130, transformers5.15.1, peft0.20.0, accelerate1.15.0, bitsandbytes0.50.2, numpy2.5.3, sklearn1.9.1, joblib1.6.0, rank-bm250.2.2 and safetensors0.8.0. The image also has cc/c++ for native code. No model downloads are needed; all permitted fixed inputs are under `/task/data` and `/task/models`. Optional modules under `/task/tools` need that directory added to `sys.path` from custom Python entry points.

The agent has14400seconds. Fresh verifier preparation has1800seconds once; each query execution has10seconds, concurrency1, three shuffled repetitions. Work must be transferred in `/app/submission`. Read the task instruction and `available_resources.md` for submission and resource rules. The verifier uses an unprivileged UID/GID10001 for submitted commands, checks one visible physical GPU, CPU/RAM/no-swap, and measures its own wall time and NVML GPU memory. The independent immutable control runs after candidate processes exit on that same device. Its overhead is separate from candidate time.

The coding agent's authorized OpenRouter transport and the independent verifier audit have network access only to openrouter.ai. Retrieval code may not use external models, corpora or APIs. Judge credentials are never passed to submitted commands. Fixed-model inference components, dtype/quantization transformations and CPU offloading are permitted; do not alter canonical model/tokenizer files or fine-tune the supplied language model. Retrieval-ranker fitting is allowed only during development.


The delivered model is the compact fixed diagnostic probe described in
available_resources.md. Training arrays are NPZ
archives; no runtime model download or omitted full checkpoint is required.

The default submission includes retriever_service.py in addition to the three
required interface files. Its all28-layer streamed inference and training-only
offset cache are already part of the immutable paired control.


## Fixed-probe API

Load /task/models/base through compact_probe.load_probe, available on /task/tools.
The returned object has model (a standard Qwen2Model decoder), config,
cpu_embedding (complete BF16 input rows), output_token_ids (sorted original IDs),
and output_rows(token_ids), returning the matching original BF16 head rows.
embed(input_ids) creates current-request GPU embeddings from the fixed CPU table.
Output matrix row numbers are internal indices; output_rows accepts original
opaque tokenizer IDs and checks membership. Use config.hidden_size dynamically.

All28 decoder layers use the serialized bitsandbytes NF4/double-quantized state,
with BF16 computation. Loading restores the serialized parameters without quantizing them again. The complete input
vocabulary is retained. The64439 output rows are the union of public training
text token IDs, training alternative-token IDs, and every vocabulary token sharing
a nonempty token_surface with those alternatives. No error queries, labels or
source-target group mappings select these rows. The fixed head covers every
delivered marked target token. probe.json records exact provenance and files.

The output head is a diagnostic subset. It supports selected source-token logits
and comparisons, rather than full-vocabulary normalized language-model loss or
unrestricted generation. The provided starting method compares source-candidate
logit masses; its denominator cancels. When multiple positions are marked, it
selects the largest candidate-source logsumexp minus the erroneous token logit,
using every supplied position. This is a retrieval feature, not full-vocabulary CE.

For a forward pass, embed the exact supplied input_ids, call model with
inputs_embeds, attention_mask and use_cache=False, then select hidden states at
j-1 for each marked position j. output_rows returns CPU weights; transfer the
needed rows to the assigned GPU and use torch.nn.functional.linear. Synchronize
before finishing the response. Current-request scores and hidden states may live
in memory but cannot be reused across requests or repetitions.

Fixed-weight gradients are permitted. For example, detach the current embedded
input, enable requires_grad, compute a selected diagnostic logit and backpropagate
to that input. The supplied probe supports this input-gradient operation. Other fixed-probe diagnostic
gradients may be implemented; no optimizer updates to the probe/tokenizer are
allowed. A separate retrieval ranker may be trained during development.



For self-built feature caches, record projection parameters, precision and
artifact hashes in `submission.json`. Training-only computation uses the stated
development or preparation budget; ranker fitting is development-only.
Current-query features, gradients and rankings must be recomputed on every
execution, including repeated query IDs. Use `score_dev.py --predictions FILE`
for public JSONL predictions with `query_id`, `ids`, `elapsed_sec`; these times
are self-reported and do not replace verifier measurements.

Keep `retriever_service.py` with the supplied `prepare.sh`. The helper's
training-only offset/source caches and token-NLL tie-break are already part
of the paired control. When altering inference or ranking, compare outputs
against the starting implementation as well as checking development quality.

The verifier requires Linux support for `SYS_PTRACE` and `CHECKPOINT_RESTORE`, granted only to its trusted supervisor for inspecting candidate file descriptors and file-backed mappings. Submitted commands run without any effective, inherited, ambient or bounding capabilities. Open-unlinked files and mappings held by preparation services count toward the same 64 GiB logical-storage limit; repeated references count once per inode.
