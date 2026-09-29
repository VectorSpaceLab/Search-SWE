# Compact Conversational Memory Question Answering

Build a compact memory and a retrieval-augmented system that answers questions about meeting transcripts.

**Task:** `task-1-x-1` · **Mode:** Implementation · **Metric:** EvidenceGroundedAnswerAccuracy

## Overview

This task covers 67 meetings from three ICSI series: Bmr (29), Bro (23) and
Bed (15). The history contains 53,600 utterances and 719,788 whitespace-delimited
words, including interruptions, references to earlier discussions, corrections
and changing proposals.

The agent receives the complete history during development and builds a
finished memory, a retriever and an answerer. Evaluation withholds the original
transcripts from all three submitted programs. Each answer must be supported by the
records retrieved from the compact memory.

## What This Task Tests

- Preserving useful information from conversations within a storage budget.
- Retrieving question-relevant evidence from a locally prepared memory.
- Producing answers grounded in the retrieved records.
- Packaging retrieval and answering for separate execution environments.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/history.jsonl` | Complete transcripts of 67 meetings |
| `data/validation/queries.jsonl` | 30 public development questions |
| `data/validation/golden_answers.jsonl` | Public reference answers and required facts |
| `data/validation/evidence.jsonl` | Transcript excerpts supporting the public answers |
| `environment/docs/` | Installed runtime and permitted API resources |

The download script restores the task's `data/` directory, mounted read-only
under `/task/data`. The 118 held-out questions concern the same history and are
disjoint from the public examples. Their answers and 1,344 supporting excerpts
are packaged under `tests/data/` and excluded from the agent environment.
Evidence provenance is checked against the supplied transcripts.

ICSI stands for **International Computer Science Institute**. The
[ICSI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/icsi/download/) contains
recorded research meetings and human transcripts; see Janin et al., *The ICSI
Meeting Corpus*, ICASSP 2003. The original license notice is included.
The 148 QA examples were authored for this task and are not original ICSI
annotations. They have transcript-linked evidence but no independent human
certification. Semantic grading remains subject to model variability.

Public assets are pinned in [assets.json](assets.json) to the
[development dataset](https://huggingface.co/datasets/hrjinbb12345/search-swe-development/tree/7fe4b0bfb7699cb393bc5b11835c47ffeb13aaec).

### Fixed Components and Allowed Changes

The history, submission interfaces and resource limits are fixed. Memory
format, information selection, indexing, retrieval and answer generation are
implementation choices. The task starts without a starter implementation.

Memory construction and retrieval may use local computation and Jina embedding
and reranking APIs. Only the answerer may call the allowed OpenRouter generation
models, subject to the [resource policy](environment/docs/available_resources.md).

### Environment and Resource Limits

The CPU Python 3.12 environment provides 8 CPUs, 8 GiB memory, 8 GiB storage
and no GPU. The agent has 120 minutes; the Harbor verifier phase has 90 minutes.
Index construction has 300 seconds. Across the question set, retrieval has 150 seconds and answering 1,800 seconds. Stage budgets do not extend the overall verifier budget.
Each answer permits at most two generation API calls, 2,000 output tokens per call and
2,000 Unicode characters in the final text.

`memory.json` is readable UTF-8 JSON and may occupy at most 183,981 bytes,
5% of the 3,679,621 dialogue-text bytes. Scripts are outside this memory budget
and contain corpus-independent code.

## Submission Contract

The deliverable is `/app/memory.json` plus the executable scripts `build_index.sh`, `search.sh` and `answer.sh`. The verifier builds an index from the memory, retrieves at most ten strings per question and passes those strings with the question to the answerer. The answerer returns plain text. Original transcripts are unavailable to the submitted programs during evaluation.

The full schema, stage permissions and invocation details live in [instruction.md](instruction.md).

## Evaluation

### Search Quality

A question scores one only when both retrieved evidence and answer correctness pass. The evidence judge accepts faithful summaries or paraphrases preserving at least one question-relevant reference fact; topic overlap alone does not count. The answer judge checks the reference answer and required facts. EvidenceGroundedAnswerAccuracy is the mean of these joint outcomes over 118 held-out questions. The report's 0–100 score is 100 times the normalized reward; evidence and answer accuracy are also reported separately.

### Correctness and Resource Gates

All three entry points, output formats, execution limits and the memory budget must
pass. Invalid output or a failed submission process invalidates the submission.
Empty retrieval is an evidence miss. A malformed judge response or model
service failure invalidates the measurement.

### Integrity Checks and Final Reward

Evidence and answer judging are separate from the trajectory audit. The audit checks task compliance and can set the whole reward to zero. An incomplete audit is an infrastructure failure. Submitted programs and the audit process do not receive the judges' provider credentials. The trajectory audit uses `deepseek-flash` through pinned RewardKit 0.1.7; evidence and answer grading use independently configured judge settings.

Task identity and execution settings are recorded in `task.toml`. Final numbering and official asset migration remain maintainer steps.

## Running This Task

From the repository root, follow the [quick start](../../../docs/quickstart.md)
to prepare the runtime and Docker. The [evaluation guide](../../../docs/evaluation.md)
explains agent and verifier configuration; the [asset guide](../../../docs/assets.md)
covers downloads and checksums.

Configure `JINA_API_KEY` for optional embedding and reranking, `OPENROUTER_API_KEY` for the submitted answerer, `ANSWER_JUDGE_*` for evidence and answer grading, and `VERIFIER_OPENAI_*` for the trajectory audit. The answerer selects among the four models in the [resource policy](environment/docs/available_resources.md); judge settings are separate. Credentials must remain outside the task package.

```bash
python scripts/download_assets.py --task-path task-submissions/haoran/1-x-1
bash scripts/run_task.sh --task-path task-submissions/haoran/1-x-1 --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and writes results under `jobs/task-submissions/haoran/1-x-1/`. Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect the launch command without starting an evaluation; it does not validate credentials, assets or API access.

## Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [task.toml](task.toml) | Task identity, artifacts, resource limits and environment variables |
| [assets.json](assets.json) | Fixed asset paths, immutable revisions and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and task environment |
| [Environment configuration](environment/docker-compose.yaml) | Read-only data mounts |
| [Verifier](tests/) | Execution, output validation and scoring |
| [Resource policy](environment/docs/available_resources.md) | Permitted API calls and credential handling |
| [Corpus license](ICSI_LICENSE.html) | ICSI redistribution terms and attribution |
