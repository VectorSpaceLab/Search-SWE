# Task: code-reranker-finetuning — Improve a fixed-candidate code reranker

Optimize the supplied `BAAI/bge-reranker-base` sequence classifier for code retrieval. The fixed first-stage retriever fuses **BM25 Top-200 and embeddings Top-200** using reciprocal rank fusion (RRF). The verifier generates these candidates independently and uses **the exact same lists** for baseline and submission. You may mine training candidates but may not change the verifier's first-stage retrieval or its candidate sets.

### Fixed hybrid retrieval

1. **Embeddings:** use the supplied, frozen `BAAI/bge-base-en-v1.5` at `/task/models/bge-base-en-v1.5` for local inference. Embed the first 512 characters of each corpus document's stripped `title + " " + text` and the first 512 characters of each question, without adding a query instruction or prefix. Load `AutoTokenizer` and `AutoModel` with `local_files_only=True`, `trust_remote_code=False`, and `use_safetensors=True` for the model. Use evaluation mode, float32, batch size 32, padding and tokenizer truncation to 512 tokens, and the final hidden state of the first (CLS) token. L2-normalize vectors and take the cosine Top-200.
2. **BM25:** use the full stripped `title + " " + text` and full question, without the embedding branch's character truncation. Lowercase and tokenize with ASCII regex `[a-z0-9]+`; no stemming or stopword removal, and each distinct query token contributes once. Fix `k1=1.2`, `b=0.75`, and positive IDF `log(1 + (N-df+0.5)/(df+0.5))`. Take exactly 200 documents, including zero-score matches if needed. The full score formula is in `/task/docs/available_resources.md`.
3. **RRF:** each branch contributes `1/(60 + rank)` for each of its 200 documents, with ranks starting at 1 and equal branch weights. Sum contributions, deduplicate and keep the **entire union**: 200–400 candidates per question depending on overlap. There is no further truncation or padding. Sort descending by RRF score; ties within either branch and in RRF use ascending document ID.

## Inputs and rules

- Work only in `/app`; `/task` is read-only. A local, unmodified reranker backbone is at `/task/models/bge-reranker-base`.
- `/task/data/corpus.jsonl` contains code records with `_id`, `title`, `text`; `/task/data/train.jsonl` contains 5,000 training records with a `query` string and `pos` and `neg` JSON arrays of code strings. Each provided record has one positive and an empty negative array. Use only these provided queries, corpus and relevance signals for training; do not use outside queries, labels, answer mappings, or hidden test data. There is **no validation split**. You may hold out part of training data yourself.
- Do not modify the verifier's fixed BM25, embedding or fusion policy, switch to a different retrieval model, add/reorder verifier candidates, or blend first-stage scores into reranker logits. The only scored changes are the reranker's weights; keep the backbone architecture, parameter names/shapes, configuration, and tokenizer unchanged. Exact reranker-score ties use the original RRF candidate order. Do not use an external reranking service.
- Both task phases run without network access or task API keys. Use only the supplied models and data; external APIs, models and retrieval/reranking services are prohibited. The embedding model is read-only and fixed; run it locally for candidate mining or self-checks. Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the installed runtime and exact local resource policy.
- Agent time limit: 6 hours. GPU resources: 1 GPU, 8 CPUs, 32 GiB RAM, 100 GiB storage. Evaluation permits up to 3 hours including local retrieval and GPU inference.
- Within evaluation, first-stage retrieval has a 2,700-second cap and evaluation of both rerankers has a 7,200-second cap; failures or timeouts keep reward at zero.

## Starter

`/app/starter/train.sh` and `train.py` provide an editable training baseline. Read `/app/starter/README.md`. Running the script samples a corpus negative per question, fine-tunes the provided reranker with a two-candidate loss, and exports `/app/output/model` without calling any API. You may change the training procedure within the rules above. For a short interface check, run `/app/starter/train.sh --max-steps 1 --batch-size 1 --max-length 32 --output-dir /app/smoke`; it does not measure retrieval quality.

## Output

Save a self-contained checkpoint at `/app/output/model` with `config.json`, `model.safetensors`, and the original tokenizer files. The verifier loads it offline using `AutoTokenizer.from_pretrained(..., local_files_only=True, trust_remote_code=False)` and `AutoModelForSequenceClassification.from_pretrained(..., local_files_only=True, trust_remote_code=False, use_safetensors=True)`. Training scripts/logs are optional. The verifier compares checkpoint structure/tokenizer with the supplied backbone; invalid or missing output receives zero.

## Metric

For each hidden question, Accuracy@5 is 1 if at least one relevant code document appears among the first five reranked candidates, otherwise 0. Baseline and submission rank the same frozen RRF candidate union with the original and submitted reranker respectively; ties use the original candidate order.

Fixed neural inference pairs the full question with the full stripped `title + " " + text`, using joint tokenizer truncation to 512 tokens and batch size 16. Only the model's single finite logit scores each pair; first-stage numerical scores are not included.

Let `B` be the original reranker's mean Accuracy@5, `S` the submitted reranker's mean Accuracy@5, and `C` the fraction of **all** hidden questions whose fixed RRF union contains at least one relevant document. `C` is the best Accuracy@5 any reranker could attain without changing those candidates. The reward is `max(0, (S − B) / (C − B))`, clamped to `[0, 1]`. If `C = B` (including no first-stage hits), reward is 0 because there is no remaining improvement headroom. Copying or worsening the baseline scores 0; reaching the attainable ceiling scores 1 when `C > B`. Queries with no relevant candidate remain in the denominators of B, S and C.

The hidden 200-question test and labels are not visible to the agent. A failed model load, retrieval or evaluation is a verifier failure, not evidence of a quality score.

For a self-check, split `/task/data/train.jsonl` locally, compare the initial and trained checkpoint scores on held-out training records, and optionally combine local BM25 Top-200 with the supplied local model's normalized embedding Top-200 using the same RRF policy. No verifier validation labels are provided.
