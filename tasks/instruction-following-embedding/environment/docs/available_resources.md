# Available resources

Use only the supplied E5-large-v2 weights, FollowIR training/development data,
corpus passages, and installed local libraries. There are no external task
APIs, model providers, retrieval endpoints, pretrained models or additional
datasets. No task API keys are injected. The coding agent's own model
transport is managed by the framework and does not grant permission for
submission API calls. Final execution is offline; the separate verifier's
OpenRouter integrity-judge key is never passed to encoding processes.

E5-large-v2 is pinned to revision
`f169b11e22de13617baa190a028a32f3493550b6` and has 24 BERT layers, hidden size
1024 and a maximum of 512 input tokens. The original model card is inside its
read-only directory and documents `query: ` / `passage: ` prefixes and masked
average pooling. Deployment uses the fixed serving strings, tokenizer and
masked mean pooling in the task instruction; optimize checkpoint weights rather than
submitted formatting/pooling code. The final document encoder must stay this
unchanged base, preserving compatibility with an existing document-vector index.
Only final query weights may change, delivered as a standard PEFT LoRA payload
of at most512KiB (524288 bytes of all JSON+safetensors; optional Markdown excluded
only from this cap). Supported weight tensors are unquantized FP16/BF16/FP32.
Full checkpoints are training-only. Full query fine-tuning and standard LoRA
are allowed, without an
imposed loss, training-batch recipe or teacher method. Training-only formatting,
multiple teacher forwards and derived examples from the training records are
allowed within the development budget. Do not use another pretrained model.

Training supervision must come only from the1717 supplied training records and examples/teachers derived from those records. The20 public groups are a validation set: use their queries, instructions and judgments only for evaluation, failure analysis and choosing global training hyperparameters or checkpoints trained on the training set. Do not put public query/instruction examples or judgments into gradient training, teacher targets, pseudo-label generation, label-aware negative mining or any other model-weight optimization. An evaluation function may read public labels to compute metrics; it must not backpropagate through them. Global checkpoint selection and scalar blending of checkpoints trained on the training set are allowed. Provided corpus passages may be used independently as unlabeled training text or document-embedding anchors, without using public query/passage relevance relationships. This separation is audited from the training code and trajectory by the integrity judge.
