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
transcripts from both submitted programs. Each answer must be supported by the
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

### Fixed Components and Allowed Changes

The history, submission interfaces and resource limits are fixed. Memory
format, information selection, indexing, retrieval and answer generation are
implementation choices. The task starts without a starter implementation.

Memory construction and retrieval must use local computation, including during
development. Only the answerer may call the configured generation API, subject
to the [resource policy](environment/docs/available_resources.md).

### Environment and Resource Limits

The CPU Python 3.12 environment provides 8 CPUs, 8 GiB memory, 8 GiB storage
and no GPU. The agent has 120 minutes; the Harbor verifier phase has 90 minutes.
Across the question set, retrieval has 150 seconds and answering 1,800 seconds.
Each answer permits at most two API calls, 2,000 output tokens per call and
2,000 Unicode characters in the final text.

The submitted memory has a 735,924-byte expanded-size budget, including relative
paths. All submitted files, including code, indexes and paths, must also fit
within 183,981 bytes on disk. These budgets are respectively 20% and 5% of the
3,679,621 dialogue-text bytes in the history.

## Submission Contract

The deliverable is a finished `/app/memory/`, executable `/app/run.sh` and
`/app/answerer/answer.sh` scripts, and their implementation files. Evaluation
uses the submitted memory without running a memory builder.

For each question, retrieval runs offline and writes at most ten records.
Answering receives only the question and those records, its corpus-independent
code and runtime dependencies. It writes a plain-text answer and may call the
configured model through the task-provided API transport.

Both stages run unprivileged with submission files read-only. The verifier
supplies the question and output paths. See [instruction.md](instruction.md)
for the complete invocation and output contracts.

## Evaluation

### Search Quality

A question scores one only when both an evidence hit and answer correctness
are accepted. The evidence judge compares retrieved text with supporting
transcript excerpts, accepting faithful paraphrases. At least one
question-relevant fact must be preserved. The answer judge checks the final
answer against its reference and required facts.

These are separate judgments: the evidence judge does not see the submitted
answer, and the answer judge does not see the retrieved records. Each uses
three calls with majority voting. EvidenceGroundedAnswerAccuracy is the mean
of the joint outcomes over the 118 held-out questions; the report also includes
`evidence_accuracy` and `answer_accuracy`.

### Correctness and Resource Gates

Both entry points, output formats, execution limits and size budgets must
pass. Invalid output or a failed submission process invalidates the submission.
Empty retrieval is an evidence miss. A malformed judge response or model
service failure invalidates the measurement.

### Integrity Checks and Final Reward

A separate trajectory and file audit checks task and resource compliance.
A violation sets the final reward to zero; an incomplete audit is an
infrastructure failure. The audit uses `deepseek-flash` through pinned RewardKit
0.1.7; evidence and answer grading use independently configured judge settings.

```text
reward = mean(evidence_hit AND answer_correct), if the compliance audit passes
score = 100 * reward
```

## Running This Task

From the repository root, follow the [quick start](../../../docs/quickstart.md)
to prepare the runtime and Docker. The [evaluation guide](../../../docs/evaluation.md)
explains agent and verifier configuration; the [asset guide](../../../docs/assets.md)
covers downloads and checksums.

Configure `ANSWER_API_KEY`, `ANSWER_API_BASE_URL` and `ANSWER_MODEL` for the
submitted answerer, `ANSWER_JUDGE_*` for evidence and answer grading, and
`VERIFIER_OPENAI_*` for the trajectory audit. These settings default to empty
values in the task configuration. The verifier's network allowlist permits
`api.deepseek.com`; using another provider requires a matching task configuration
change. Credentials must remain outside the task package.

```bash
python scripts/download_assets.py --task-path task-submissions/haoran/1-x-1
bash scripts/run_task.sh --task-path task-submissions/haoran/1-x-1 --model "YOUR_AGENT_MODEL"
```

Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
the launch command without starting an evaluation. Task-local checks can be run
with `python -m unittest discover -s task-submissions/haoran/1-x-1/tests -p 'test_*.py'`.

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

## Data Provenance and Limitations

ICSI stands for **International Computer Science Institute**. The
[ICSI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/icsi/download/) contains
recorded research meetings and human transcripts; see Janin et al., *The ICSI
Meeting Corpus*, ICASSP 2003. The original license notice is included.
The 148 QA examples were authored for this task and are not original ICSI
annotations. They have transcript-linked evidence but no independent human
certification. Semantic grading remains subject to model variability.

Public assets are pinned in [assets.json](assets.json) to the
[development dataset](https://huggingface.co/datasets/hrjinbb12345/search-swe-development/tree/7fe4b0bfb7699cb393bc5b11835c47ffeb13aaec).
Official asset migration and final task numbering remain maintainer steps.

Compressed-memory accounting can undercount deeply nested, concatenated or
oversized streams. This issue must be fixed before release.
