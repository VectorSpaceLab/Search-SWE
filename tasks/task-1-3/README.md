# Scientific-Paper Question Answering

Build a RAG system that answers scientific questions and identifies the supporting paper.

**Task:** `task-1-3` · **Mode:** Implementation · **Metric:** LLMJudgeAccuracy

## Overview

Finding a related paper is only one part of scientific question answering.
The system must recover relevant evidence from PDFs, interpret it, and
produce an answer attributable to the correct source.

This task combines retrieval and generation over 300 local research papers.
It evaluates the complete pipeline: an otherwise plausible answer receives no
credit when the submitted evidence document is wrong. It also tests whether
the system can share its index and services reliably across concurrent questions.

## What This Task Tests

- Turning scientific PDFs into searchable representations with document provenance.
- Connecting retrieved evidence to concise answers.
- Maintaining attribution across parsing, retrieval, and generation.
- Sharing a retrieval service safely across concurrent query processes.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 300 research-paper PDFs |
| `data/validation/queries.jsonl` | 25 public development questions |
| `data/validation/golden_answers.jsonl` | Public answers and supporting document IDs |

Public assets are mounted under `/task/data`. The 25 held-out questions use
the same PDF corpus, but their questions and labels are separated from the
agent environment. [Task 1-4](../task-1-4/README.md) instead evaluates page
localization within previously unseen long PDFs.

### Fixed Components and Allowed Changes

The corpus and output interface are fixed. PDF processing, index design,
retrieval, evidence selection, and answer synthesis are implementation choices.
Optional OpenRouter and Jina services are subject to the
[resource policy](environment/docs/available_resources.md); they do not permit
replacing corpus-grounded work with external answers.

### Environment and Resource Limits

The CPU Python 3.12 environment provides 16 CPUs, 64 GiB memory, 100 GiB storage,
and no GPU. The agent has two hours and the Harbor verifier four hours.
The submitted build has a 3,600-second limit. The verifier launches up to five
query processes at once, each with 900 seconds from process start; queue time
is excluded and workers share the same resources.

The verifier also bounds query execution, answer scoring, and trajectory review
as stages inside its overall budget. Stage limits do not extend that budget.

## Submission Contract

The deliverable is `/app/build.sh` plus `/app/run.sh` and the implementation
they need. Each query produces a concise `answer` and one evidence document ID,
along with its query ID. The build must recreate any service in the separate
verifier, and the query path must support concurrent invocations.

The full schema and invocation details live in [instruction.md](instruction.md).

## Evaluation

### Search Quality

A question scores one only when **both** conditions hold: the evidence document
matches the reference, and an answer judge accepts the answer as semantically
equivalent to the reference. LLMJudgeAccuracy is the mean of these binary
outcomes over 25 hidden questions. The report's 0–100 score is 100 times the
normalized reward.

### Correctness and Resource Gates

Execution, complete query coverage, non-empty answers, valid document IDs, and
runtime limits must pass. A failed query process or structurally invalid output
invalidates the submission, rather than merely counting as an incorrect answer.

### Integrity Checks and Final Reward

The answer judge and trajectory audit are separate. The first evaluates answer
equivalence; the second checks task compliance and can set the whole reward
to zero. Their credentials are isolated from submission processes and from
each other.

The package retains its source task's PDF and question data. Current task
identity and execution settings are recorded in `task.toml`; historical
migration identifiers are not needed to run it.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

This task needs both `ANSWER_JUDGE_*` settings for answer scoring and
`VERIFIER_OPENAI_*` settings for the trajectory audit. Optional submission APIs
use shared `OPENROUTER_API_KEY` and `JINA_API_KEY`. The launcher guide explains
the separate credential groups and their API requirements.

```bash
python scripts/download_assets.py --task task-1-3
bash scripts/run_task.sh --task task-1-3 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-1-3/`.
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
| [Resource policy](environment/docs/available_resources.md) | Allowed submission APIs and model restrictions |
