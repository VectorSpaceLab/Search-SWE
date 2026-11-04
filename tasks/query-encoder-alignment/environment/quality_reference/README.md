# Frozen 0.6B quality reference (ridge-v1)

Copy this directory to a writable location. Fit once using only the public corpus and the corresponding fixed vectors:

```bash
cp -r /app/quality_reference /app/submission
python /app/submission/baseline.py --fit --doc-vectors /task/data/doc.npy --projection /app/submission/ridge.npz
/app/submission/run.sh --doc-vectors /task/data/doc.npy --queries /task/data/validation/queries.jsonl --output /app/public-results.jsonl --top-k 1
```

The backbone is frozen Qwen3-Embedding-0.6B at the manifest pin. All corpus rows are encoded in their original order, without a prompt, using only `text`. Queries use exactly `Instruct: Given a claim, find documents that refute the claim.\nQuery:` followed by their unchanged text. Tokenization uses left padding, truncation to 512 tokens, batch size 32, and the final non-padding token. Inference uses BF16, eager attention, eval mode, seed 0 and deterministic PyTorch algorithms. No backbone weights are trained. Token representations are normalized in FP32.

For corpus features X and the original target vectors Y, fit `W = solve((X-muX).T@(X-muX) + I, (X-muX).T@(Y-muY))` in FP64. Alpha is exactly 1.0 on the sum of squares, with an unregularized intercept. Save W, muX and muY in FP32. At inference normalize `(x-muX)@W+muY` in FP32, then use inner products with the original unmodified document matrix. No relevance labels or validation/hidden queries are used to fit the projection. Encoding public corpus text for fitting query-side parameters is permitted; replacing the fixed retrieval vectors is prohibited.

Exclude every result with the query's ID or with identical canonical text: `" ".join(unicodedata.normalize("NFKC", text).split()).casefold()`. This comparison uses the full `text`, not truncated tokens, and excludes all copies. Sort by descending score, breaking ties by original corpus row; fill the requested count after filtering. The reference code ranks the whole corpus so duplicate counts and ties cannot cause an incomplete result.

The verifier independently fits this exact baseline and measures its Accuracy@1 on the same held-out queries as the submission. That measured value is A0. It is the quality anchor, separate from the 4B time reference. Implementation/configuration and data pins define the baseline version.
