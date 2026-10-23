# Available resources

Only the mounted vector assets and installed runtime are task resources. The supported languages are ar, zh, en, fr, hi, it, ja, pt, ru and es. `/task/data/train/<language>.vectors.npy` contains 200,000 raw FP16 1024-vectors per language; `/task/data/probe/<language>.vectors.npy` contains 20,000, with matching opaque uint64 `<language>.ids.npy` files. All training, probe and public development assets may inform work during the six-hour agent phase. Original-document/identifiable-translation families do not cross training/probe. Sources, encoding and representation are described below; no original text or alignment IDs are provided.

`/task/data/corpus/belebele/` and `/task/data/corpus/xquad/` each contain `documents.jsonl` (`id`, `language`) and `vectors.npy` with matching rows. These are complete pools of 4,880 and 1,440 documents, searched separately. Development directories `/task/data/development/<dataset>/` contain `queries.jsonl`, `vectors.npy`, and `qrels.jsonl` (`query_id`, `relevant_doc_ids`), for 1,830/1,308 public queries. Each query has all ten/six aligned cross-language positives. Hidden queries/qrels/alignment families are not mounted in the agent. Document/query metadata IDs are for data correspondence and development supervision; they are not transform inputs.

There is no raw text, multilingual-E5 encoder checkpoint, additional pretrained weight, external retrieval/reranking/generation API or submission-service credential. Do not fetch alternative data/models/services. Coding-agent transport is separate and is not a task API. No secret is required in the submitted program. Do not access or expose framework/model transport credentials.

`/task/baselines` provides optional reproducible simple transforms. `/task/data/baselines` contains the four public-candidate-fitted parameter archives with their per-method specifications; the baseline programs can also refit them from the provided candidates. The score uses B=0.9127469497437668 and U=0.9353486724891793 as defined in the task instruction. No additional reference weights are provided. Only Q improvement receives points; speed/GPU savings/language count are diagnostic.


## Encoding and split semantics

All vectors use `intfloat/multilingual-e5-large` revision
`3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`, with 1,024 output dimensions.
Query inputs use `query: `; document/train/probe inputs use `passage: ` in
every language. Right truncation is at 512 total tokens. Encoder computation
uses FP16; attention-masked mean pooling accumulates in FP32 without L2
normalization, and stored vectors are FP16. Transforms receive these raw vectors
cast to FP32; the scorer normalizes transformed outputs once for FP32 cosine.

Training data comes from aligned mMARCO passages and fixed MIRACL corpus shards.
The source population contains the first 1,200,000 aligned mMARCO passage IDs
per language and two MIRACL shards for ar/zh/en/fr/hi/ja/ru/es; it/pt use mMARCO
only. Exact original-text families and identifiable translations stay together.
Sections from the same MIRACL page also stay together. Short text is merged
only within the same language and train/probe side to form 250–500-token
segments. IDs are opaque and do not expose translation alignment.

Belebele/XQuAD passage, translation and question families stay on the same
public/hidden side. Exact and near-duplicate families (character-5-gram
Jaccard >=0.85) stay together. Each query searches its complete dataset pool
with all ten or six positive translations. Source texts and identifiable
training fragments are separated from evaluation questions/passages.

Sources: mMARCO revision `6d039c4638c0ba3e46a9cb7b498b145e7edc6230`, MIRACL
`d921ec7e349ce0d28daf30b2da9da5ee698bef0d`, Belebele
`7899cdfa4e1e0d733fd77c848e2c273cb1d32be2` and XQuAD
`51adfef1c1287aab1d2d91b5bead9bcfb9c68583`. Encoder and LangSAE code notices
are MIT; Belebele/XQuAD specify CC BY-SA 4.0. MIRACL specifies Apache 2.0
and documents its Wikipedia source. mMARCO's card specifies Apache 2.0
while its repository LICENSE contains CC BY 4.0; both source notices apply
to the provenance description and are not a claim of unrestricted reuse.
