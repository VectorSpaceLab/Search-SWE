# Long-PDF Evidence Localization

Find the physical pages in a long PDF that support a natural-language information need.

**Task:** `task-1-4` · **Mode:** Implementation · **Metric:** Page Recall@5

## Overview

This task is a natural-language version of finding a passage inside a document.
The target PDF is already known; the system must identify where relevant
evidence occurs, rather than retrieve a different document or generate an answer.

The challenge is to preserve the connection between searchable content and its
original physical page. Useful semantic matches can span sections or use
different wording from the question. Public and hidden queries search the same
2,043-page PDF of *War and Peace*, with different passages labelled in each split.

## What This Task Tests

- Extracting and indexing long PDFs while retaining physical page provenance.
- Translating an information need into relevant page-level results.
- Returning supporting text that actually appears on each selected page.
- Rebuilding the pipeline in a fresh verifier and sharing its index across concurrent queries.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/lp4P6AUxur.pdf` | One shared 2,043-page PDF |
| `data/validation/queries.jsonl` | 10 public development queries |
| `data/validation/golden_answers.jsonl` | Public physical-page labels and evidence excerpts |

The verifier evaluates 10 hidden queries against the same PDF. Public and hidden
query IDs, question texts, and labelled pages are disjoint. IDs are independent
opaque identifiers, and each split is shuffled so query order does not indicate
page position. Input records contain `query_id` and `query`; the sole PDF is
inferred without a `target` field.

Hidden questions and labels remain in `tests/data/` and are excluded from the
agent environment. Public validation is excluded from the verifier's mounts.

### Fixed Components and Allowed Changes

The target document, physical page numbering, and five-result interface are
fixed. Parsing, chunking, indexing, and page ranking may change. Optional
OpenRouter and Jina resources follow the
[resource policy](environment/docs/available_resources.md).

### Environment and Resource Limits

The CPU Python 3.12 environment has 16 CPUs, 64 GiB memory, 100 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has three hours.
The submitted build receives up to 2,400 seconds. Each hidden query runs in its
own process with a 900-second limit and up to five processes in parallel.
All queries share a 1,800-second execution budget; unfinished or unlaunched
queries at the deadline score zero. The outer runner allows another 60 seconds
for cleanup. Workers share the same CPU, memory, index, and build-started service.

The verifier stages the shared PDF read-only and supplies its paths to the
submission. The build must recreate the service in the fresh verifier environment.

## Submission Contract

The system is delivered through `/app/build.sh` and `/app/run.sh`. For each
question it returns five distinct, ranked physical page numbers, supporting
text, and numeric scores. Page numbers are **one-based PDF page positions**,
which may differ from printed page labels.

See [instruction.md](instruction.md) for the exact interface. This task returns
evidence locations; [task 1-3](../task-1-3/README.md) returns answers with
document-level attribution.

## Evaluation

### Search Quality

For each query, Recall@5 is the fraction of its relevant pages found among
the five returned pages. The metric is the arithmetic mean of these fractions
across all ten hidden queries. A failed or invalid query contributes zero and
remains in the denominator. The report also shows 100 times this mean before
the trajectory audit; final reward uses the 0–1 scale.

### Correctness and Resource Gates

Each query must return five valid unique pages and evidence text belonging to
those pages, with finite scores in the required order. A failed or timed-out
process, missing output, or invalid result makes only that query score zero.
Shared build/setup failure prevents all queries from scoring. Per-query timing
and execution errors are recorded in the verifier's private `query_execution.json`.

### Integrity Checks and Final Reward

Page relevance is scored deterministically against labels; there is no
answer-correctness model. A separate trajectory audit checks compliance.
Final reward is mean Recall@5, including zeros for failed or invalid queries,
when the trajectory audit passes. A failed audit makes the whole reward zero.
The audit uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 with
verifier-only endpoint and key settings.

## Running This Task

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the trajectory judge's `VERIFIER_OPENAI_*` settings. This task does
not need `ANSWER_JUDGE_*`. Optional submission APIs use shared OpenRouter
and Jina keys. Downloading restores the shared PDF and public validation files;
Compose keeps private queries and labels out of the agent environment.

```bash
python scripts/download_assets.py --task task-1-4
bash scripts/run_task.sh --task task-1-4 --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/task-1-4/`.
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
| [Resource policy](environment/docs/available_resources.md) | Permitted submission APIs |
