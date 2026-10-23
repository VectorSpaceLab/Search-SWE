# ChunQiu Temporal Retrieval

Current run and release status (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md). Earlier validation-stage statements are superseded by that dated record.

Author: **Bingyu**. Local task package, version **0.1.0**.

Retrieve original event records for reign-based dates and time windows in
Classical Chinese annals. Return up to ten records from the complete corpus.
The submission may use the supplied local model and the documented APIs.
No starter implementation or author baseline is included in the agent files.

## Data and audit

Source: [official ChunQiuTR](https://github.com/xbdxwyh/ChunQiuTR/tree/392d6ec8d62de8256b3b45578f7b4484c22042ce),
commit `392d6ec8d62de8256b3b45578f7b4484c22042ce`.
[Paper](https://aclanthology.org/2026.findings-acl.612/).

| Input | Records |
| --- | ---: |
| Shared corpus | 18,662 |
| Public labeled queries | 6,617 |
| Public training-month document associations | 19,452 |
| Hidden test queries | 778 |
| Public validation queries | 0 |

The corpus preserves every original event/comment text after removing all
1,510 synthetic no-event placeholders. Record IDs are replaced bijectively by
opaque IDs; corpus order is deterministically shuffled. The source's original
train/test month assignments are retained. Validation queries and the 305
cross-split windows are omitted. Only training-month associations appear in
`dated_examples.jsonl`, including repeated commentary associations.

Coarse event-presence filtering initially produced 8,829 training and 1,146
test candidates. The final content audit excludes questions containing a
missing month, any calendar-only positive, or a positive whose exact text also
occurs under a nonrelevant corpus ID. It also excludes the `向前推` and `附近`
window templates because their anchor/radius interpretation is unclear.
Exclusion reasons can overlap. Query text is never rewritten. For each retained
question, the only qrel edit is removing source no-event positives; no new gold
is generated. No filter depends on a model's predictions.

Corpus records contain only `doc_id,text`; public examples contain
`query_id,text,relevant_doc_ids`; dated examples contain
`doc_id,time_text,reign,year,month`. Hidden query and qrel files use the usual
`query_id,text` and `query_id,relevant_doc_ids` schemas. Private calendar labels
and original source IDs are never exposed to the submission.

The reproducible builder, source hashes, complete inclusion/exclusion ledger,
ID maps and screening evidence are in
`task_development/chunqiu-temporal-retrieval` in the surrounding author workspace.
The audit checks content, query templates and identical-text contradictions;
it is not a new philological validation of every historical passage. Text-only
records can still require difficult contextual temporal inference.

See [LICENSE.data.md](LICENSE.data.md) for source and model notices. Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

## Runtime and scoring

One A100 40GB, 16 CPUs, 32 GiB RAM, 100 GiB storage; development is six hours.
Both images use the repository GPU image. `build.sh --corpus --index-dir` has
1,200 seconds for indexing and initialization. After it returns successfully,
`run.sh --index-dir --queries --output --top-k 10` receives the complete hidden
batch and has **120 seconds**, including all local work and API waits. Batching
is allowed. No query input is exposed during build.

Score is the mean **binary nDCG@10**, directly in [0,1]; displayed percentages
multiply it by 100. DCG sums `1/log2(rank+1)` over relevant returned IDs. IDCG
uses `min(10, number of event positives)`. Hitting one of several positives is
not full credit. There is no baseline subtraction.

Missing/duplicate query outputs, invalid IDs/scores/order, command failure,
build/batch timeout or a confirmed integrity violation gives zero. The grader
checks coverage and output semantics, not a prescribed retrieval method.
The entire batch must complete within the deadline; partial output is not
credited after a timeout. A required trajectory-judge failure also fails closed
and must be reported separately from retrieval quality.

The separate verifier runs submission code as UID 10001 under read-only /app,
with only its index/output locations writable. The corpus, model and docs are
mounted read-only. Public examples are not mounted in verification. Hidden
labels, grader code, audit credentials, trajectories and reward logs remain
root-private. Query order and request IDs are refreshed at verification time.

## Structural references and validation

Reviewed base: `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`.
`tasks/reasoning-query-rewriting` supplies the full-corpus CLI and separate
verifier/API boundary; `tasks/query-encoder-alignment` supplies GPU/model-mount
precedent. Current local quantity-aware-retrieval and decision-model-training
provide the user-approved document style and whole-batch timing pattern.
Data, thresholds and policies were established for this task. Command fences
in instruction.md follow the user's explicit formatting preference.

See [VALIDATION.md](VALIDATION.md) for executed commands, evidence and unrun
layers. A local smoke implementation is not a coding-agent trial or proof of
difficulty for a tuned system. Author baselines remain outside this package.

Local checks from the repository root:

```bash
python scripts/download_assets.py --task chunqiu-temporal-retrieval --verify-only
python -m unittest discover -s tasks/chunqiu-temporal-retrieval/tests -p 'test_*.py'
python scripts/check_tasks.py tasks/chunqiu-temporal-retrieval
```

Public data pins are present. See RUN_RESULTS.md for current trial evidence and VALIDATION.md for historical author-stage checks.
