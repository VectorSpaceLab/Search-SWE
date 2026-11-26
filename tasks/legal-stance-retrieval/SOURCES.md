# Sources and Preparation

## Source and annotation record

Upstream repository [CaseFacts](https://github.com/idirlab/CaseFacts).

Downloaded commit: `16a4072067c39daa463495e10e3bb029c29beb5b`.
The downloaded repository README identifies the paper as *CaseFacts: A Benchmark
for Legal Fact-Checking and Precedent Retrieval*, links IDIRLab/CaseFacts on
Hugging Face and advertises CC BY-NC 4.0. The collected GitHub repository metadata
has `license: null`; this is not a basis for claiming unrestricted redistribution.
Preserve the source attribution and noncommercial notice for derived data.
The source's case summaries retain Oyez URLs and original metadata. No new
court facts or precise decision dates were invented.

| Original file | SHA-256 |
| --- | --- |
| `supreme_court_cases.json` | `fbbc56fb34a0d5b2b7303d22d88699b2e6edac71d40aa09d3d5b9d230bcf47a5` |
| `train.json` | `c3bddcb5c520824cb8b6dd612830e1095bf4041e0de7b7f03cb40456aef45936` |
| `test.json` | `57823bf939cec038d813ab75d8a4a79b411e4b3207fa83f2dfbedde2d32864c2` |

The full corpus is the earlier deterministic shuffled JSONL conversion: all
3,126 source records, stable opaque IDs, all original source fields and rendered
case/term/facts/question/conclusion text. Its SHA-256 is
`5e83cadbf0d47762a1a3aadb0883aaed6ce5d155206c22b4b6c1d89523cb8fc5`.
The model card declares Apache-2.0 for Qwen3-Embedding-0.6B. Exact model file pins
and hashes are in `assets.json`.

The annotation lineage is retained outside agent mounts at
`task_development/legal-precedent-retrieval/screening/official-test-cleaning`:

- `cleaned/manifest.jsonl` accounts for every original binary test row.
- `agent-source-decisions.json` and `agent-pair-decisions.json` distinguish final
  review decisions from raw local model proposals.
- `cleaned/test/evidence.jsonl` retains accepted stance, original case text and
  reasons; `cleaned/test-cases.md` is the readable review record.
- `training-overlap-decisions.jsonl` and `test-dedup-decisions.json` record the
  reviewed proposition exclusions without removing every shared case.
- `cleaned/validation.json` and `checksums.json` preserve export verification.

Packaging copies the accepted test query/qrels bytes unchanged. Training query
rows retain only `query_id`, `query`, `stance`; original positive document-ID
seeds become binary `relevance` maps. The original training labels are not
claimed as fully corrected. An `all` training example therefore has the same
known positive seeds as its source direction, not a guarantee of exhaustive
support/refutation coverage. Training and all-mode variants remain associated
through their input IDs for agent-chosen splitting.

The 311 frozen test propositions are quality-selected, not selected for poor
model scores. Binary relevance reflects recorded majority holdings even when a
historical rule later changed. These judgments do not certify current legal
validity. All accepted positives have explicit review decisions, but unreviewed
pairs can still contain missed positives; the metric uses the frozen pooled
qrels and treats other IDs as zero gain. The original packaging step did not publish data or model assets; later publication status is recorded in [the validation history](VALIDATION.md#recorded-model-run) and pinned in [assets.json](assets.json).

Public packaging now uses `data/examples`. The source query ID prefix `train_` is replaced bijectively by `example_` in both examples files. Original source IDs remain in the author audit; no query text, stance, case ID or relevance map changes. The frozen hidden query IDs and qrels are untouched.
