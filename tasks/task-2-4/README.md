# Task-2-4: BrowseComp-Plus Multi-Constraint Retrieval

Optimize the ReAct starter to return exactly five distinct corpus document IDs
for each multi-constraint question. The sole metric is macro Gold Recall@5.
This task was migrated from `harbor/tasks/task-1-6`, retaining its corpus and
allowed retrieval resources.

## Task contents

| Path | Purpose | Visibility |
| --- | --- | --- |
| `data/corpus.jsonl` | Full BrowseComp-Plus corpus | Shared read-only input |
| `data/validation/queries.jsonl` | 20 public development questions | Agent-visible |
| `data/validation/qrels_gold.txt` | 63 public gold relevance labels | Agent-visible |
| `tests/data/queries.jsonl` | 20 held-out questions | Verifier-only |
| `tests/data/qrels_gold.txt` | 63 hidden gold relevance labels | Verifier-only |
| `environment/docs/` | Runtime and allowed API resources | Agent-visible |

The task installs a ReAct starter under `/app/starter`, with executable
`/app/build.sh` and `/app/run.sh` wrappers. The Agent improves or replaces the
baseline while preserving these interfaces. Each output line
contains `query_id` and a `doc_ids` array of exactly five distinct strings that
match corpus `docid` values.

The public assets follow the [asset directory convention](../../docs/assets.md):
they live outside Docker build contexts, and `assets.json` records their sizes
and SHA-256 checksums. The verifier mounts only the corpus, while its hidden
inputs are packaged under `/tests/data` in the verifier image.

## Validation and test splits

Each split is a stratified 20-question subset of its prior 30-question split,
selected with seed `20260909`. The source dataset has 830 questions, including
725 with 1–5 gold documents. The current gold-count distribution is:

| Gold documents per question | Validation questions | Test questions |
| --- | --- | --- |
| 1 | 3 | 3 |
| 2 | 4 | 4 |
| 3 | 4 | 4 |
| 4 | 5 | 5 |
| 5 | 4 | 4 |
| Total | 20 | 20 |

Each split contains 63 question–gold-document pairs, averaging 3.15 gold
documents per question. Gold Recall@5 has a theoretical ceiling of 1.0 on both
splits. This is a gold-count-stratified selection rather than an estimate of
performance over the full dataset's natural distribution.

Question text comes from `dataset/qa_ground_truth.jsonl`; positive document
labels come from `dataset/qrels_gold.txt`. Every selected gold ID was checked
against the task corpus. Validation is sampled first; test candidates exclude
its query IDs and gold document IDs.

The packaged query and relevance files preserve this selection. `assets.json`
records the exact public file sizes and SHA-256 checksums. The task package
contains questions and document relevance labels; answer labels are not used.

## Runtime and credentials

Both Dockerfiles use the existing benchmark base image
`search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0`. This local image must be
available before building the task.

The environment uses 32 CPUs, 128 GiB RAM, 200 GiB storage, and no GPU. Agent and
verifier timeouts are 7,200 and 15,600 seconds respectively. The verification
subprocess has a 15,300-second shared budget, including a 600-second build
limit and 120 seconds for scoring. There is no individual query timeout;
queries share the remaining execution budget. Harbor allows a further 300
seconds for finalization. Each query may use at most 20 retrieval rounds.

Use the shared optional `OPENROUTER_API_KEY` and `JINA_API_KEY` from
[`.env.example`](../../.env.example). Harbor injects those names into both
task environments. SiliconFlow is not an available resource. This task needs
neither trajectory nor answer-judge settings. Coding-agent configuration follows the launcher's
`AGENT_*` group. Allowed OpenRouter generation models may support query decomposition, rewriting, and
relevance reasoning. The scoring code uses only the Python standard library
and needs no API credentials or network access. Submission execution retains
its configured access to the permitted APIs.

## Verification and scoring

Harbor transfers `/app` and the Agent trajectory to a separate verifier. The
submission is rebuilt and run as UID/GID 65534. It can write to `/app`, temporary
storage, and the query output directory; evaluation reports, hidden labels,
and final rewards remain verifier-owned.

The verifier builds once and invokes `run.sh` once per hidden question, using a
pool of five concurrent workers. Each query has separate input, output, and
stdout/stderr log files; the service and index are shared. Queries have no
individual timeout. Results and timings
are merged in input order regardless of completion order. Run-phase elapsed
time records wall time, with summed query durations reported separately.

For a valid submission, it computes each query's retrieved gold count divided by its
gold count, then takes the arithmetic mean across all 20 queries. The five
positions are weighted equally, and gold documents are counted once per query.

`reward.txt` contains that mean in `[0, 1]`; `reward.json` contains only the
`gold_recall_at_5` metric. The evaluation report also expresses it on a 0–100
scale and records per-query counts and recall. Failed execution, missing or
extra query outputs, invalid IDs, duplicates, or any result with a document
count other than five invalidate the entire submission and receive zero.

Local unit tests:

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

The standalone evaluator can score a validation result file with:

```bash
python3 tests/evaluate.py \
  --corpus data/corpus.jsonl \
  --queries data/validation/queries.jsonl \
  --qrels data/validation/qrels_gold.txt \
  --predictions /path/to/results.jsonl \
  --report /tmp/task-2-4-validation.json
```

No Oracle solution is included. Synthetic fixtures check the submission
interface and scoring; the measured baseline results are described below.

## ReAct baseline and checks

The [starter README](environment/starter/README.md) describes the editable
SQLite FTS5/BM25 service and search/observation loop. It indexes the first
6,000 characters of each document, uses an allowed OpenRouter planner when
configured, and otherwise performs one lexical search. The loop caps searches
at 20 and writes a diagnostic trace beside the results. Arbitrarily rewritten
submission code must still honor this limit; the trace is not trusted proof of
its actual internal search count.

The offline baseline was checked in a network-disabled container on the full
100,195-document corpus: construction took about 38 seconds, and all 20 public
queries ran successfully through five workers. Its public Gold Recall@5 was
`0.1741666667`. Index reuse and service restart also passed. This is a basic
lexical baseline measurement, not a measurement of the model-driven planner.

Local tests cover scoring, five-worker execution, early finish, follow-up
searches from observations, and the 20-search cap. External model calls are
simulated in tests; no live judge or planner credentials are used.
