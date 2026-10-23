# Agentic Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `agentic-search` |
| Version | 1.0.0 |
| Authors | Search-SWE |
| Primary metric | GoldRecall@5 |
| Compute | 32 CPUs; 16 GiB RAM; 200 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 17100 s |
| Dataset | BrowseComp-Plus |
| Hidden queries | 20 |

Improve a ReAct search system's document coverage on BrowseComp-Plus questions.

### Overview

BrowseComp-Plus questions often require combining several constraints.
A search system may need to decompose a question, inspect intermediate results,
and reformulate its search before choosing its final documents.

This task supplies an editable ReAct starter built around SQLite FTS5/BM25.
The agent improves or replaces its retrieval and reasoning components while
working within a bounded number of searches. Evaluation measures the documents
ultimately retrieved, not the fluency of an answer or the appearance of a trace.
The current repository identifier is `agentic-search`.

### Task Setup

#### Provided Assets

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

#### Fixed Components and Allowed Changes

The corpus, five-document output, and resource limits are fixed. Indexing,
document coverage, query planning, retrieval, observations, and selection may
change. The initial starter indexes the first 6,000 characters of each document
and uses an allowed OpenRouter planner when configured; without a key it
falls back to one lexical search.

Optional APIs follow the [resource policy](environment/docs/available_resources.md).
Each question may use at most **20 retrieval rounds**; independent searches in
a batch count separately. A submission-generated trace is diagnostic, not
trusted proof of compliance.

#### Environment and Resource Limits

The CPU Python 3.12 environment provides 32 CPUs, 16 GiB memory, 200 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has 17,100 seconds.
A shared 15,300-second verification budget includes a 600-second build cap and
120 seconds reserved for scoring. Five query workers share the remaining budget;
there is **no individual query timeout**.

A recorded local run of the offline lexical baseline completed a full-corpus
build in about 38 seconds and achieved public Gold Recall@5 of `0.1741666667`.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Turning compound information needs into effective search actions.
- Using observations to improve later retrieval and final document selection.
- Balancing document coverage with a finite retrieval-round budget.
- Serving concurrent questions through a shared index and search service.

## Verification Explanation

### Submission Contract

The deliverable contains `/app/build.sh`, `/app/run.sh`, and the implementation.
The verifier rebuilds once and launches one query process per question with up
to five workers. The service and index are shared, while input/output files are
separate.

Each result contains a query ID and exactly five distinct corpus IDs in `doc_ids`.
This differs from the scored `results` objects used by several other tasks.
See [instruction.md](instruction.md) for the exact contract.

### Evaluation

#### Search Quality

For each query, Gold Recall@5 is the number of retrieved gold documents divided
by its gold count. Reward is the arithmetic mean across 20 queries, in `[0, 1]`.
All five positions are weighted equally; this is neither answer accuracy nor
a rank-discounted metric. The evaluation report also gives a 0–100 score.

#### Correctness and Resource Gates

Failed execution, missing or extra query outputs, unknown or duplicate document
IDs, or a result count other than five invalidate the whole submission.
The build, shared execution budget, concurrency contract, and search-round
limit remain task requirements.

#### Integrity Checks and Final Reward

Gold Recall@5 remains the deterministic quality metric. Every run also applies
`tests/jailbreak_judge/codex.toml` to the transferred agent trajectory and
submission. The pinned RewardKit 0.2.0 judge uses `deepseek/deepseek-v4.1-flash`
through OpenRouter. A violation zeros the entire reward; missing trajectory,
credentials, judge failure or malformed output leaves zero and invalidates the run.
Submission processes are stopped before judging and never receive judge keys.

The evaluator writes `task-score.txt` and `task-score.json` with raw recall.
`reward.txt` contains the gated score; `reward.json` contains numeric
`gold_recall_at_5`, `jailbreak_judge`, and `reward`. The 17,100-second verifier budget
includes the original 15,300-second execution budget and judge overhead.
Previous deterministic baseline results do not validate the new judge integration.

### Running This Task

Run task-local regression tests without API calls:

```bash
python -m unittest discover -s tasks/agentic-search/tests -p 'test_*.py'
```

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure `VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` and
`VERIFIER_OPENAI_API_KEY` with an OpenRouter key in the ignored host `.env`.
No answer-judge credentials are needed. Environment/agent and verifier allow
`openrouter.ai` and `api.jina.ai`; judge keys are mapped only into the verifier.
Optional submission APIs use shared `OPENROUTER_API_KEY` and `JINA_API_KEY`;
the coding agent still needs its own launcher configuration.

For an existing public prediction file, the deterministic scorer can also be
run from the repository root:

```bash
python tasks/agentic-search/tests/evaluate.py \
  --corpus tasks/agentic-search/data/corpus.jsonl \
  --queries tasks/agentic-search/data/validation/queries.jsonl \
  --qrels tasks/agentic-search/data/validation/qrels_gold.txt \
  --predictions /path/to/results.jsonl \
  --report /tmp/agentic-search-validation.json
```

This scores predictions; it does not reproduce the full Harbor execution.
Local fixture tests are available via
`python -B -m unittest discover -s tasks/agentic-search/tests -p 'test_*.py' -v`.
No oracle solution is included.

```bash
python scripts/download_assets.py --task agentic-search
bash scripts/run_task.sh --task agentic-search --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/agentic-search/`.
Replace `YOUR_AGENT_MODEL` with your configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

### Task Files

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

## References

None.
