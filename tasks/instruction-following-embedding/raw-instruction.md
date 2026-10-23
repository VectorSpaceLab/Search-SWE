# Instruction-following Embedding

## Task Description

Adapt the query weights of supplied E5-large-v2 so a news-retrieval application
can change relevance instructions without changing the query, candidate set or
existing document-vector space. Many tenant-specific query adapters share the same
base and document index, so each final deployment increment has a512KiB budget.
The final document encoder stays the supplied base.
Optimize the harmonic mean of the three subset FollowIR p-MRR values over
the fixed untrained E5 serving baseline, retaining both versions' relevance. Favor
positive instruction following across every subset. Training is the expected route but
is optional. Do not substitute FollowIR-7B or cross/generative rerankers.

## Requirements

- Train on the1717 supplied training records, their derived examples/teachers,
  and independent unlabeled corpus text/document anchors.
- Public20 query/instruction/qrels are validation-only: evaluation, failure
  analysis and global training-hyperparameter/checkpoint selection are allowed.
- Never use public query/instruction examples or judgments for gradient/model-
  weight optimization, teacher targets, pseudo-labels or label-aware negatives.
  Reading public labels in a no-gradient metric calculation is allowed.
- Global scalar blends of train-set-trained checkpoints may be selected on
  public metrics. Do not turn public validation into parameter fitting.
- Integrity review audits this provenance from training code and trajectory.

### Model submission and encoding contract

- Training may use full E5 fine-tuning, standard LoRA, larger train-set-derived
  teachers, compression, custom losses/negatives and training-only formats.
  All training remains inside the120-minute development and shared budgets.
- Only final query weights may change. The final document_checkpoint is literal
  "base", preserving the supplied document-vector space. Final query_checkpoint
  is "base" or a safe relative directory holding standard PEFT LoRA.
- The final deployment payload is at most512KiB, exactly524288 bytes: sum the
  logical file sizes of every safetensors and JSON file below /app/submission.
  Optional Markdown is excluded only from this deployment cap and still counts
  toward32GiB task storage. Supplied base weights are outside the payload.
- LoRA directories use adapter_config.json and adapter_model.safetensors with
  unquantized FP16/BF16/FP32 tensors. FP8, integer/other quantized formats,
  custom adapters, auto_mapping, modules_to_save and layer_replication are
  unsupported. Adapter rank, target layers and training algorithm are otherwise
  free within the payload/architecture limits. The trusted loader merges the
  adapter into the supplied base offline. Full checkpoints are training-only.
- Submit /app/submission/submission.json with exactly query_checkpoint and
  document_checkpoint plus the referenced adapter. Optional Markdown is allowed.
  No submitted Python, custom tokenizer/formatting/pooling/head, optimizer,
  pickle/bin/pt files, symlinks, special files or document cache.
- Deployment uses the supplied base tokenizer, normal special tokens, right
  truncation to512, bf16/SDPA, equal attention-masked float32 mean pooling
  including special tokens and L2 normalization. The query string is exactly
  `query: {query}\nInstruction: {instruction}`; document input is `passage: {text}`,
  where text is `(title+' '+passage).strip()`.
- Each deployed query/instruction, including warmups, executes exactly one
  complete E5 forward: one sequence, batch1, <=512 tokens, standard2-D binary
  padding mask, embeddings and every BERT layer once. No additional encodings,
  altered layers, output transforms or forward-counter changes. Violations are
  global model failures. Training/development may use multiple forwards and
  other pooling/formatting within the same development budget.
- The final document tower is the unchanged supplied E5 base. Training-only
  document models and teachers may change. Documents are independently encoded
  once and reused; their vectors cannot depend on query, instruction,
  batching/order or other documents. The query worker receives only its own
  query/instruction and final weights, without candidates/labels/document cache.
  No request-history use or test-time weight update. Outputs are finite nonzero
  1024-vectors; the supplied24-layer BERT architecture is preserved.
- No external model/data/API, hidden-data access, answer mappings, cross-encoder
  or generative reranker, privileged operation, or evaluation manipulation.
  Do not change read-only inputs, tests, reward, timing/process boundaries,
  trajectory records or collection boundaries.

## Available Validation Data

- Read-only E5-large-v2 `/task/models/e5-large-v2`, revision
  f169b11e22de13617baa190a028a32f3493550b6, 24 BERT layers, 1024-dimensional
  hidden states, maximum 512 tokens. Deployment tokenizer, format and pooling are fixed.
- `/task/data/train.jsonl`: 1717 filtered FollowIR-train records, fields
  query/instruction/document/label/score/id; 59 source topic-overlap records
  removed from 1776. Labels true/false; no imposed contrastive-batch recipe.
- `/task/public/dev-groups.json`: 20 public groups (10 Robust04, 4 Core17,
  6 News21), original/changed instructions, all original 1000 candidates,
  original/changed qrels and changed-document IDs.
- `/task/corpus/{robust04,core17,news21}.jsonl`: 47492/19899/30921 passage
  records, `_id`, `title`, `text`; document text `(title+' '+text).strip()`.
- 84 hidden groups (42/16/26), preserving all 104 source groups; both versions
  and connected near-duplicate topics remain on the same side. Source benchmark
  is test-only; this is a separate Search-SWE development/test partition.
- `/task/docs/{environment,available_resources}.md` and
  `/task/runtime/evaluate.py`, public metric and loading utilities.
- Optional reproducible baseline command `python /task/baselines/baseline.py`,
  initial-model cache under /app/baseline-cache; counts toward dev time/storage.

## Expected Artifacts

Submit `/app/submission/submission.json` and its referenced standard PEFT LoRA directory, or select
the unchanged base. No launch script or custom serving code is submitted. Optional Markdown is
permitted within total storage.

## Verification

### Metrics and failure handling

- Each subset p-MRR in [-1,1] uses the official changed-document rank ratio,
  changed-document average then query average. Rank1001 for changed judgment
  outside candidates. Report their arithmetic mean P as diagnostic; do not use(P+1)/2.
- Score metric H=3/(1/P_robust04+1/P_core17+1/P_news21) when all subset values
  are positive, else H=0. Equal-weight harmonic aggregation emphasizes balanced
  improvements and is Search-SWE-specific, not the official arithmetic macro.
- Six nDCG@10 retention gates R>=rho*R0. Linear gain; all-qrels IDCG. R0 fixed
  query-only E5. rho is fixed at 0.9.
- B=max(0,H) of the eligible fixed-format untrained E5 baseline. Query-text-only E5 defines R0 relevance floors, not the deployed B baseline.
  U is harmonic H of a same-model/resource compact-query fixed-serving weight-adaptation
  reference selected only on public data before its hidden check. Frozen
  B=0, U=0.07054277758767746, rho=.9.
- Score 100*clip((H-B)/(U-B),0,1) after relevance/model/resource gates; framework
  reward score/100. Integrity rejection or failed/unavailable mandatory judge0.
- Either version invalid/nonfinite/wrong-dimension/zero/timeout/failure -> pair
  p-MRR and both versions' relevance0, all denominators retained.
- At the120-minute development cutoff, stop task processes and collect the
  last submission. A valid artifact is graded even if the agent times out or
  has not produced a final reply. Missing/incomplete/invalid submission0.
  Preparation/model/global resource failure or verifier/required-judge timeout0.
- Report H, diagnostic macro P, per-subset p-MRR, two-version nDCG@10/nDCG@5/MAP, valid groups, times and
  resource peaks. Speed is not independently weighted. Judge health is separate.

| Subset | R0 original | R0 changed | Minimum original (90%) | Minimum changed (90%) |
|---|---:|---:|---:|---:|
| robust04 | 0.4467470613991606 | 0.2748072857676422 | 0.4020723552592446 | 0.247326557190878 |
| core17 | 0.3518920171806676 | 0.1713133745500164 | 0.3167028154626008 | 0.1541820370950148 |
| news21 | 0.4467375457681735 | 0.26275469786118 | 0.4020637911913562 | 0.236479228075062 |

### Timing and resource protocol

- 16 CPU / 32 GiB shared RAM / 32 GiB task storage / one A100-SXM4-40GB.
- 120-minute agent phase includes preprocessing, all training, tuning and
  public evaluations. No external submission resources or keys. Coding-model
  transport belongs to framework; verifier-only integrity key stays private.
- Task writes under /app (28 GiB tmpfs), /tmp (1 GiB tmpfs), plus fixed input
  bytes within 32 GiB total; tmpfs consumes the 32 GiB RAM cgroup. Framework
  setup/logs/collection staging exempt; do not use them to bypass task storage.
- Final preparation <=3600 seconds includes model load, complete 98312-document
  independent encoding/cache, query process startup and three fixed public
  warmup requests. Document batches <=32. No submitted document cache accepted.
  Singleton/batch normalized-vector cosine check >=.999 allows measured bf16
  GEMM roundoff; semantic query/batch independence remains mandatory.
- Per version <=1 second, concurrency1; includes encode, transfer, normalize,
  all-candidate scoring/sorting. No document re-encoding during query phase.
- Verifier normalizes vectors in float32, ranks original 1000 candidates by
  cosine descending, equal scores retain source candidate order. It produces
  complete rankings internally; submission never returns just Top-10.
- Encoders run as UID10001 with read-only submission/model, restricted file
  reads, scratch-only writes, no network and process cleanup. Submit weights for the provided fixed runtime; no custom services, launch scripts or background jobs.
- Public check `python /task/runtime/evaluate.py --groups
  /task/public/dev-groups.json --output /app/public-evaluation`; full corpus
  re-encoding counts toward development time. Faster independent dev code allowed.

## Hidden Test Overview

The separate verifier holds 84 groups (42 Robust04, 16 Core17, 26 News21). Original/changed versions
and connected repeated topics remain on the same side of the 20/84 split.

## Environment and available resources

Before implementing the system, read the following read-only task documents:

- `/task/docs/environment.md` — installed runtime, paths, permissions and public execution tools.
- `/task/docs/available_resources.md` — supplied data/models, use restrictions, sources and license notices.

The coding agent's provider connection does not grant task-program API access.
Follow this task's resource permissions; only the declared artifacts transfer
to the separate verifier.
