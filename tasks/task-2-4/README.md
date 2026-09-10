# Agentic Search Optimization

Improve a ReAct search system's document coverage on BrowseComp-Plus questions.

**Task:** `task-2-4` · **Mode:** Optimization · **Metric:** Gold Recall@5

## Overview

BrowseComp-Plus questions often require combining several constraints.
A search system may need to decompose a question, inspect intermediate results,
and reformulate its search before choosing its final documents.

This task supplies an editable ReAct starter built around SQLite FTS5/BM25.
The agent improves or replaces its retrieval and reasoning components while
working within a bounded number of searches. Evaluation measures the documents
ultimately retrieved, not the fluency of an answer or the appearance of a trace.
The current repository identifier is task 2-4.

## What This Task Tests

- Turning compound information needs into effective search actions.
- Using observations to improve later retrieval and final document selection.
- Balancing document coverage with a finite retrieval-round budget.
- Serving concurrent questions through a shared index and search service.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | The 100,195-document BrowseComp-Plus corpus |
| `data/validation/queries.jsonl` | 20 public development questions |
| `data/validation/qrels_gold.txt` | Public gold document relevance labels |
| `environment/starter/` | Editable ReAct loop, lexical service, and entry points |

The verifier has 20 separate questions and gold labels. Both splits have
1–5 gold documents per question, with matching gold-count distributions:
3, 4, 4, 5, and 4 questions respectively. Each split contains 63 gold pairs.
The sampling seed is `20260909`; test selection excludes validation query IDs
and gold document IDs.

This stratified subset has a theoretical Gold Recall@5 ceiling of 1.0.
It is not an estimate over the full dataset's natural question distribution.
Answer labels are not used.

### Fixed Components and Allowed Changes

The corpus, five-document output, and resource limits are fixed. Indexing,
document coverage, query planning, retrieval, observations, and selection may
change. The initial starter indexes the first 6,000 characters of each document
and uses an allowed OpenRouter planner when configured; without a key it
falls back to one lexical search.

Optional APIs follow the [resource policy](environment/docs/available_resources.md).
Each question may use at most **20 retrieval rounds**; independent searches in
a batch count separately. A submission-generated trace is diagnostic, not
trusted proof of compliance.

### Environment and Resource Limits

The CPU Python 3.12 environment provides 32 CPUs, 128 GiB memory, 200 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has 15,600 seconds.
A shared 15,300-second verification budget includes a 600-second build cap and
120 seconds reserved for scoring. Five query workers share the remaining budget;
there is **no individual query timeout**.

The previously documented offline lexical baseline completed a full-corpus
build in about 38 seconds and achieved public Gold Recall@5 of `0.1741666667`.
That is a historical local measurement, not a new run or a result for the
model-driven planner.

## Submission Contract

The deliverable contains `/app/build.sh`, `/app/run.sh`, and the implementation.
The verifier rebuilds once and launches one query process per question with up
to five workers. The service and index are shared, while input/output files are
separate.

Each result contains a query ID and exactly five distinct corpus IDs in `doc_ids`.
This differs from the scored `results` objects used by several other tasks.
See [instruction.md](instruction.md) for the exact contract.

## Evaluation

### Search Quality

For each query, Gold Recall@5 is the number of retrieved gold documents divided
by its gold count. Reward is the arithmetic mean across 20 queries, in `[0, 1]`.
All five positions are weighted equally; this is neither answer accuracy nor
a rank-discounted metric. The evaluation report also gives a 0–100 score.

### Correctness and Resource Gates

Failed execution, missing or extra query outputs, unknown or duplicate document
IDs, or a result count other than five invalidate the whole submission.
The build, shared execution budget, concurrency contract, and search-round
limit remain task requirements.

### Integrity Checks and Final Reward

This task uses **neither an answer judge nor a trajectory judge**. The evaluator
is deterministic and its sole quality metric is Gold Recall@5. Runtime isolation
and output validation remain in place; removing model-based judges does not
relax the restrictions on hidden labels or unauthorized resources.
For valid execution, `reward.txt` contains mean recall and `reward.json`
contains `gold_recall_at_5`.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

No `ANSWER_JUDGE_*` or `VERIFIER_OPENAI_*` settings are required for this task.
Optional submission APIs use shared `OPENROUTER_API_KEY` and `JINA_API_KEY`;
the coding agent still needs its own launcher configuration.

For an existing public prediction file, the deterministic scorer can also be
run from the repository root:

```bash
python tasks/task-2-4/tests/evaluate.py \
  --corpus tasks/task-2-4/data/corpus.jsonl \
  --queries tasks/task-2-4/data/validation/queries.jsonl \
  --qrels tasks/task-2-4/data/validation/qrels_gold.txt \
  --predictions /path/to/results.jsonl \
  --report /tmp/task-2-4-validation.json
```

This scores predictions; it does not reproduce the full Harbor execution.
Local fixture tests are available via
`python -B -m unittest discover -s tasks/task-2-4/tests -p 'test_*.py' -v`.
No oracle solution is included.

```bash
python scripts/download_assets.py --task task-2-4
bash scripts/run_task.sh --task task-2-4 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-2-4/`.
Replace `YOUR_AGENT_MODEL` with your configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

## Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [task.toml](task.toml) | Task identity, artifact collection, and phase budgets |
| [assets.json](assets.json) | Fixed asset paths, immutable revisions, and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and task environment |
| [Environment configuration](environment/docker-compose.yaml) | Read-only mounts and hardware requests |
| [Verifier](tests/) | Execution, output validation, and scoring implementation |
| [Starter notes](environment/starter/README.md) | ReAct loop, lexical fallback, and service design |
| [Resource policy](environment/docs/available_resources.md) | Allowed models and API operations |
