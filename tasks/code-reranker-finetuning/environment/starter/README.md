# Minimal reranker fine-tuning baseline

Run `/app/starter/train.sh` to train the local BGE reranker on the supplied training records and save `/app/output/model`. It makes no API calls and never modifies the first-stage retriever. The baseline uses one positive and one sampled corpus negative per question and a two-candidate cross-entropy loss. Known positives for a question are excluded from its negative pool. Unlabelled documents are assumed negative; these are weak negatives, not new relevance judgments.

The supplied `pos` and `neg` fields are JSON arrays; all supplied `neg` arrays are empty. Increasing a training group size without first supplying negatives is not enough. A single-candidate group has identically zero cross-entropy and zero learning signal, so this starter always constructs two candidates.

Defaults: one epoch, two queries (four pairs) per batch, max length 512, FP32, gradient checkpointing, AdamW at 2e-5. No validation data are supplied. You may edit training code and mine better negatives with local BM25 or the frozen encoder at `/task/models/bge-base-en-v1.5`. First-stage retrieval follows the fixed policy in `/task/docs/available_resources.md`.

For a small interface smoke test use a fresh directory:

```bash
/app/starter/train.sh --max-steps 1 --batch-size 1 --max-length 32 \
  --output-dir /app/smoke
```

`--device cpu` is available for local smoke tests. Existing nonempty checkpoint directories are refused rather than deleted. Checkpoint export uses safetensors and copies the original config and tokenizer files byte-for-byte to satisfy the verifier.
