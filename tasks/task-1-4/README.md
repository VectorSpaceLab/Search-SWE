# Long-PDF Evidence Localization

Find the physical pages in a long PDF that support a natural-language information need.

**Task:** `task-1-4` · **Mode:** Implementation · **Metric:** Page Recall@5

## Overview

This task is a natural-language version of finding a passage inside a document.
The target PDF is already known; the system must identify where relevant
evidence occurs, rather than retrieve a different document or generate an answer.

The challenge is to preserve the connection between searchable content and its
original physical page. Useful semantic matches can span sections or use
different wording from the question. A system must generalize its parsing
and retrieval approach to new PDFs, not just build a lookup for development documents.

## What This Task Tests

- Extracting and indexing long PDFs while retaining physical page provenance.
- Translating an information need into relevant page-level results.
- Returning supporting text that actually appears on each selected page.
- Rebuilding the pipeline on unseen documents within a fixed resource budget.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | Six public development PDFs |
| `data/validation/` | 30 public queries and page relevance labels |
| `data/verifier/corpus/` | Six different PDFs mounted only for verification |

The verifier evaluates 30 hidden queries against held-out PDFs. Neither the
PDFs nor the questions are the public examples. Query IDs are local to each
split and can repeat without referring to the same question.

Held-out PDFs are downloadable assets but excluded from the agent's mounts;
hidden questions and labels remain in `tests/data/`. This is environment
isolation, not a claim that repository readers cannot inspect published files.

### Fixed Components and Allowed Changes

The target document, physical page numbering, and five-result interface are
fixed. Parsing, chunking, indexing, and page ranking may change. Optional
OpenRouter and Jina resources follow the
[resource policy](environment/docs/available_resources.md).

### Environment and Resource Limits

The CPU Python 3.12 environment has 16 CPUs, 64 GiB memory, 100 GiB storage,
and no GPU. The agent has two hours; the Harbor verifier has three hours.
The submitted build receives up to 2,400 seconds, followed by one 1,800-second
query run covering all 30 questions.

The verifier stages a different PDF collection and supplies its paths to the
submission. Development-time services and indexes cannot be assumed to survive.

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
across hidden queries. The report also expresses normalized reward on a 0–100 scale.

### Correctness and Resource Gates

Results must cover every query, reference valid unique pages in the target PDF,
and include evidence text belonging to those pages. Ranking, execution, and
resource checks must pass before the metric is accepted.

### Integrity Checks and Final Reward

Page relevance is scored deterministically against labels; there is no
answer-correctness model. A separate trajectory audit checks compliance.
Final reward is mean Recall@5 when execution, output, and audit checks pass,
and zero otherwise.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the trajectory judge's `VERIFIER_OPENAI_*` settings. This task does
not need `ANSWER_JUDGE_*`. Optional submission APIs use shared OpenRouter
and Jina keys. Downloading also restores the held-out PDF assets; Compose keeps
them out of the agent environment.

```bash
python scripts/download_assets.py --task task-1-4
bash scripts/run_task.sh --task task-1-4 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-1-4/`.
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
