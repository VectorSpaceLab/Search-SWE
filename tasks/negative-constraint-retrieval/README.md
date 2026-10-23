# Negative-constraint retrieval

Current run and release status (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md). Earlier validation-stage statements are superseded by that dated record.

Build a Top-1 search engine over 8,011 fixed passages. The 20 authored queries
require a named subject and semantic exclusions such as roles, events, named
works, institutions or other content. There are 10 public validation and 10
hidden test queries, with 19 subject groups and no subject overlap between folds.
Each query has one author-reviewed compliant passage; the 20 positives are distinct.

The deterministic score is hidden Accuracy@1, correct predictions / 10.
A query timeout or valid incorrect prediction loses only that query's credit;
evaluation continues and all 10 queries remain in the denominator. Other invalid
execution/output still gives zero for the submission. A required RewardKit trajectory audit separately enforces the
resource and integrity policy; an unavailable or failed audit gives zero final
reward and is an infrastructure failure, not evidence of poor retrieval.

## Fixed inputs and provenance

The original text comes from `xgl-git/NS-IR-main` at historical commit
`ebdfa4f62b3c2af01d43cf30560910fba3003c73`, archive `NegConstraint.zip` with SHA-256
`a10dc25f13b816b4cd7c17c221b2916a97c981b0b8f086dbf3826a1c6e47cbfe`.
Its 3,946 raw document IDs become 3,907 documents after exact-text deduplication.
All original passage texts and IDs remain unchanged. Version 0.3.0 adds 4,104
source-conditioned passages generated locally with Qwen3.5-9B across 365 topic
cohorts: 3,889 background passages and 215 evaluated-subject negatives. The same
generation, fact-preservation and automatic filtering policy covers both groups.
Eight passages received source-based family-relationship corrections; sampled
unsupported details, truncations and duplicate generations were removed.
Queries and relevance decisions are newly authored;
original qrels are not used as the new ground truth. Some corpus paragraphs look
constructed; this package does not claim that all are original Wikipedia excerpts.

Every document receives an opaque random ID, independently of a shuffled row
order. Original numeric IDs, provenance, label files, baseline outputs and the
private ID map/seed are absent from Agent mounts and build context. The pair with
original ID 10221 is therefore neither numerically identifiable nor adjacent to
its original partner by construction order. Randomization is not a guarantee
against every possible corpus shortcut; original and generated passage styles
remain visible. All 8,011 rows were shuffled together after augmentation.
Queries also receive opaque IDs. The two Henry Avery queries share a fold.

For the original corpus, the author inspected every complete passage matching
the required subject names. Every admitted new matching passage preserves an
affirmative, author-reviewed fact that violates at least one query exclusion;
new Avery passages violate both Avery queries. Whole-corpus subject scans verify
that the 20 original unique positives remain the only compliant passages.
Generation factual review was sampled, with source corrections recorded in the
author ledger. These are assistant annotations, not independent human adjudication
or exhaustive certification of every generated factual detail.

The upstream dataset redistribution-license question remains unresolved. Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

## Difficulty evidence

Version 0.3.0 expands the corpus while retaining the 20 conversational queries,
labels, unique-positive texts, 8-second deadline and 4-CPU verifier. Evaluated
subjects now have 6–20 matching passages, and 346 additional background cohorts
also receive generated passages. No query, label, split, source map or generation
marker is added to corpus records.

An offline comparison of the frozen v0.2.2 Luna implementation gives hidden gold
ranks `[11,12,6,6,14,15,13,10,20,11]`, median 11.5, versus median 2 before expansion.
Its Top-8 recall falls from 10/10 to 2/10; always selecting the second candidate
falls from 9/10 to 0/10. Full-query BM25 with the same tokenizer (`k1=1.5,b=.75`)
has hidden median gold rank 12.5 and Top-8 recall 2/10. These protocols are
recorded in `corpus-expanded-v030/rank-comparison.json`; they are distinct from
the older screening protocols below. Queries and augmentation were frozen
before measuring these ranks or replaying the API. Style clues may remain, and
low scores from a frozen Top-8 solver do not establish difficulty for a fresh
agent that can adapt its retrieval strategy.

The frozen submission replay scores **0/10 public and 0/10 hidden** with its
original internal timeouts plus the 8-second grader. Removing query-related
waiting limits gives **0/10 public and 2/10 hidden**. No grader query times out;
all unlimited test invocations also finish within 8 seconds. Eight hidden gold
passages are absent from the Top-8 pool. The other two encounter the program's
own HTTP read timeout in the original setting and are answered correctly in the
unlimited replay. This is a raw-score diagnostic using the real grader, not a
fresh coding-agent Harbor trial or an audited final reward. Full evidence is in
`task_results/negative-constraint-retrieval/frozen-luna-expanded-v030-20261014T113140Z/`
in the surrounding workspace.

The following v0.2.x results use the earlier 3,907-document corpus.

Version 0.2.2 rewrites all 20 queries again as conversational reading requests.
They use preferences, questions, reading context and references across sentences,
without repeated accept/reject explanations. The common requirement to name the
requested subjects now appears once in the task instruction; surnames suffice
for people. Preferences to leave content out remain hard exclusions, and allowed
exceptions retain their scope. Corpus text, query/document IDs, labels and the
10/10 split are unchanged. The 8-second deadline and per-query timeout scoring
from v0.2.1 are unchanged. The author-only before/after ledger and semantic review
are in `task_development/negative-constraint-retrieval/construction/natural-language-v3/`.
The historical `freeze_task_dataset.py` is guarded against overwriting v0.3.0;
use the audited `corpus-expanded-v030` artifacts for the expanded version.

The following screening results describe **the original wording**, not the current queries. All 20 original queries fail Top-1 for four fixed local baselines: BM25, BGE-M3 dense,
Qwen3-Embedding-8B, and Qwen3-Reranker-8B over the union of each retriever's Top-100.
The first three score all 3,907 documents. The reranker evaluates the candidate
union; the claim is not an exhaustive full-corpus reranking experiment. Each
failure has a strictly higher-scoring wrong-document witness, so corpus shuffle
or tie-breaking cannot remove it. The stronger negative-constraint reranker
instruction solves 3/20; 17/20 remain misses. Many gold documents rank second:
these are Top-1 failures, not necessarily Top-10 failures. Selection against
these baselines is deliberate and does not imply unseen Agents will fail.

For v0.2.0, the same fixed BM25 protocol scores 1/10 on public queries and 0/10 on hidden queries. The archived luna local fallback with API calls disabled scores 2/10 public and 0/10 hidden; these are historical offline diagnostics, not a coding-model trial of the current revision.

For v0.2.2, frozen-wording offline diagnostics give BM25 0/10 on each split
and the archived luna fallback 3/10 public, 0/10 hidden. The fallback's candidate
recall at 8 is 8/10 public and 7/10 hidden. These mixed changes do not establish
that a new coding agent will score lower; no query was retuned using the results.

One v0.2.2 Harbor trial of Codex + OpenRouter `openai/gpt-6-luna`, effort `max`,
scored raw 1/10 on hidden queries, with no query timeouts and 3.318–5.032 seconds
per query. Public self-tests scored 10/10. Final Harbor reward was zero because
RewardKit retried an already completed audit after a recovered stream event and
exhausted its audit deadline. v0.2.3 fixes that transport handling, with unchanged
queries, retrieval scoring and budgets. A verifier-only regrade is prepared but
awaits explicit approval after an automatic approval rejection; it has not run.
See `VALIDATION.md` for evidence and the limits of this single trial.

The Agent implements the search engine under `/app` from the documented interfaces.
Author construction evidence lives outside this task package at
`task_development/negative-constraint-retrieval/construction/final-20/` in the
surrounding author workspace, including `review.md` and `evidence.jsonl`.

## Interface, runtime and isolation

`instruction.md` is the complete Agent request; `raw-instruction.md` is its
structured authoring source. Corpus records use `doc_id,text`, queries use
`query_id,text`, and ground truth uses `query_id,relevant_doc_ids` (singleton).
The engine returns one `results` item with `doc_id` and a finite numeric `score`.

Runtime: 4 CPU cores, 32 GiB RAM, 100 GiB storage, no GPU; Agent phase 7,200 s;
build 1,800 s. Verification builds once and runs queries sequentially in separate
invocations, each with one input row and an 8-second wall-clock deadline (3-second
base plus 5-second fixed network allowance). Startup, index loading and all API
waits count; budgets cannot be pooled. A query timeout scores zero only for that
query, ignores its output, and preserves evaluation of all remaining queries.
Each invocation has distinct input/output files; its process group is terminated
on timeout while build-started services remain available. Build failures/timeouts
and non-timeout execution/output errors still invalidate the submission.
The CPU allocation does not cap asynchronous API concurrency. Local GPUs were used only for author-side screening and corpus generation. The user chose the existing CPU/API resource profile for submissions.
OpenRouter/Jina retrieval and the three explicit Qwen generation models are
permitted. Generation may check constraints on supplied passages, in addition to
query rewriting. No external web or benchmark lookup is permitted.

Only `/app` and the Agent trajectory are transferred. The verifier rebuilds in
a fresh directory as UID 10001 using `runuser`, `setpriv --no-new-privs`, an
explicit environment and process timeouts. `/app` is read-only to the submission;
only index/cache/temp and output locations are writable. `/tests`, labels,
trajectory and reward logs are root-private. Judge credentials are not passed
to submitted programs. Both phases use the pinned repository CPU base image.

## Validation and local configuration

From the Search-SWE root:

```bash
python scripts/download_assets.py --task negative-constraint-retrieval --verify-only
python scripts/check_tasks.py tasks/negative-constraint-retrieval
python -m unittest discover -s tasks/negative-constraint-retrieval/tests -p 'test_*.py'
docker build -t search-swe-local:nc-agent tasks/negative-constraint-retrieval/environment
docker build -t search-swe-local:nc-verifier tasks/negative-constraint-retrieval/tests
```

The strict task/release check reports the three unpublished revisions until
publication; it must not be made green using fabricated SHAs. Author staging
checks use `check_release(..., packages=[task], allow_unpublished=True)` with the
local task-only staging manifest. See `VALIDATION.md` for actual executed checks
and remaining prerequisites. Static checks and deterministic fixtures are not
an end-to-end coding-model trial.

For a future configured trial, preserve any existing ignored checkout `.env`
and set the chosen coding model/provider and its credential, for example
`AGENT_MODEL` and `AGENT_OPENROUTER_API_KEY`. The required trajectory judge needs
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` and
`VERIFIER_OPENAI_API_KEY`. Optional submission resources need
the shared `OPENROUTER_API_KEY` and/or `JINA_API_KEY`, as in `agentic-search`.
Do not share secret values in chat or write them into artifacts. The archived v0.1.1 luna trial achieved 8/10 with about 59 seconds for the whole batch; it does not validate the revised setting. The v0.2.2 trial and pending v0.2.3 audit regrade are recorded above. For a separately authorized fresh trial, launch with
`bash scripts/run_task.sh --task negative-constraint-retrieval` and the chosen
model/provider flags, previewing with `--dry-run` first.

## Structural precedent

Reviewed base: `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`.
`tasks/reasoning-query-rewriting` supplied the full-corpus search CLI,
CPU/API budgets, separate-verifier isolation, RewardKit 0.2.0 integration,
and final reward gating. Its corpus, queries, gold, metric and narrower
generation-use restriction were not inherited. This task uses Accuracy@1,
unique-positive semantic constraints and allowed query-passage reasoning.
The task name is absent from the local base and existing directories; active
remote PR collision checking was not performed. The two existing repository test
inventories and the network-policy table were extended with this task's network
profile and RewardKit use.
Existing unrelated network-policy and join-aware task changes were preserved.
