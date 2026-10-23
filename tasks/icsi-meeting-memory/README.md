# Compact Conversational Memory Question Answering

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `icsi-meeting-memory` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | EvidenceGroundedAnswerAccuracy |
| Compute | 8 CPUs; 8 GiB RAM; 8 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 5400 s |
| Dataset | ICSI Meeting Corpus |
| Hidden queries | 143 |

Build a compact memory and a retrieval-augmented system that answers questions about meeting transcripts.

### Overview

The complete meeting history is available during development, but the submitted
system must answer from a finished memory occupying at most five percent of the
dialogue text. Index construction, retrieval and answering run separately.
Only the question and retrieved notes reach the answerer.

The history covers 67 meetings from three series: Bmr (29), Bro (23) and Bed (15).
It contains 53,600 utterances and 719,788 whitespace-delimited words.
The task evaluates both the evidence preserved in memory and the answers
supported by that evidence.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/history.jsonl` | Complete transcripts of 67 meetings |
| `data/validation/queries.jsonl` | Five public development questions |
| `data/validation/golden_answers.jsonl` | Public reference answers and required facts |
| `data/validation/evidence.jsonl` | Supporting transcript excerpts |

Public inputs are mounted read-only under `/task/data`. The 143 held-out
questions concern the same history and are disjoint from the five public
examples. Their questions, answers and evidence are in `tests/data/` and
excluded from the agent environment.

The [ICSI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/icsi/download/) contains
research-meeting recordings and human transcripts. ICSI stands for
International Computer Science Institute; the corpus is described by Janin
et al., *The ICSI Meeting Corpus*, ICASSP 2003. The original
[license notice](ICSI_LICENSE.html) is included.
The 148 question-answer examples were authored for this task, are linked to
transcript evidence, and are not original ICSI annotations. They have not
received independent human certification.

The history is pinned in [assets.json](assets.json). The public examples are restored from bundled
`asset-metadata/validation/` files.

#### Fixed Components and Allowed Changes

The history, submission interfaces, memory budget and execution limits are
fixed. Memory structure, information selection, indexing, retrieval and
answer generation are implementation choices. No starter is supplied.

Local computation and Jina embedding and reranking APIs are available for memory
preparation and retrieval. Only the answerer may use the four allowed OpenRouter
generation models, subject to the [resource policy](environment/docs/available_resources.md).

#### Environment and Resource Limits

The CPU Python 3.12 environment provides eight CPU cores, 8 GiB RAM,
8 GiB storage and no GPU. The agent has two hours; the verifier has 90 minutes.
Both Compose overlays enforce the eight-core quota.

Index construction has 300 seconds. Retrieval across all questions has
150 seconds, and answering has 1,800 seconds. These stage limits do not extend
the overall verifier budget. Each answer permits at most two generation calls,
2,000 output tokens per call and 2,000 Unicode characters in the final text.

The readable UTF-8 `memory.json` file may occupy at most 183,981 bytes,
five percent of the 3,679,621 dialogue-text bytes. Its formatting and metadata
count toward this limit. The three scripts contain corpus-independent code and
are outside the memory-file budget; the index is built from that memory during
evaluation.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Preserving useful conversational information within a fixed memory budget.
- Retrieving relevant evidence from the prepared memory.
- Answering from the retrieved notes without consulting the original history.
- Rebuilding and running the pipeline under separate stage permissions.

## Verification Explanation

### Submission Contract

Deliver exactly `/app/memory.json` and executable `/app/build.sh`,
`/app/run.sh` and `/app/answer.sh`. Each script is self-contained.
The build creates an index from the submitted memory. Search returns a JSON
array of at most ten memory strings for one question, and the answerer returns
plain answer text using only that question and those strings.

The four files are transferred into a separate verifier. Each submitted command
runs as a non-root user with its own stage inputs and writable working directory.
Original transcripts, hidden references and judge credentials are inaccessible
to the submitted commands. Jina and OpenRouter requests use credential-isolated
transports during evaluation.

See [instruction.md](instruction.md) for the full interface and
[raw-instruction.md](raw-instruction.md) for its structured authoring source.
Only the rewritten instruction and the mounted data and resource documentation
are exposed to the agent.

### Evaluation

#### Search Quality

For each question, credit requires both an evidence hit and a correct answer.
A hit means that the retrieved notes faithfully preserve at least one relevant
reference fact, including valid summaries or paraphrases. Topic overlap alone
does not count. The answer judge checks the reference answer and required facts.
Evidence is judged without the answer, and the answer is judged without the
retrieved notes.

EvidenceGroundedAnswerAccuracy is the mean of these joint binary outcomes over
143 held-out questions.
Evidence and answer accuracy are also reported separately. Semantic grading
remains subject to model variability.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.06293706293706294` and integer score anchor `a = 20` on the 0–100 scale:

```text
reward(q) = (a / 100) * q / b                             if 0 <= q <= b
            a / 100 + (1 - a / 100) * (q - b) / (1 - b)  if b < q <= 1
```

This maps raw quality 0, b and 1 to rewards 0, a / 100 and 1. Raw quality and
auxiliary diagnostics are reported separately. Harbor retains the 0–1 reward
precision; a displayed 0–100 score is rounded to one decimal place.
Correctness and trajectory-audit gates take precedence over this conversion.

#### Correctness and Resource Gates

The four files, executable permissions, JSON syntax and size, index build,
script completion and output formats must satisfy the contract. A failed
submitted process or invalid output invalidates the submission. Empty retrieval
is an evidence miss. A malformed judge response or model-service failure
invalidates the measurement rather than establishing model quality.

#### Integrity Checks and Final Reward

The evidence and answer judges are separate from the trajectory audit.
The audit checks task compliance and can set the entire reward to zero.
An incomplete audit is an infrastructure failure.

The trajectory audit uses `deepseek/deepseek-v4.1-flash` via OpenRouter through
pinned RewardKit 0.2.0. Evidence and answer judging use the separately configured
`ANSWER_JUDGE_MODEL_NAME`. Submitted build, search and answer processes receive
restricted API transports rather than provider credentials. The separate,
non-root trajectory-audit process holds its own model credential. Its shell-tool
environment filters credential variables, and an inherited Landlock policy
limits filesystem access to read-only audit inputs and runtime files, with
writes confined to audit state and output directories.

### Running This Task

Follow the repository [quick start](../../docs/quickstart.md) to prepare Harbor
and Docker, the [evaluation guide](../../docs/evaluation.md) for model
configuration, and the [asset guide](../../docs/assets.md) for fixed inputs.

Optional retrieval calls use `JINA_API_KEY`, and the submitted answerer uses
`OPENROUTER_API_KEY`. Evidence and answer grading use `ANSWER_JUDGE_MODEL_NAME`;
the current configuration routes those calls through OpenRouter with
`VERIFIER_OPENAI_API_KEY`. Trajectory auditing uses `VERIFIER_OPENAI_BASE_URL`
and `VERIFIER_OPENAI_API_KEY`. These are verifier-only credentials and must not
be exposed to submitted programs.

The commands below run the package at `tasks/icsi-meeting-memory/`.

```bash
python scripts/download_assets.py --task icsi-meeting-memory
bash scripts/run_task.sh --task icsi-meeting-memory --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; it does not validate
assets, credentials or API access. Use a fresh output directory for each run.

### Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing request and executable contract |
| [raw-instruction.md](raw-instruction.md) | Structured authoring source, excluded from agent mounts |
| [task.toml](task.toml) | Identity, transferred artifacts and resource limits |
| [assets.json](assets.json) | Fixed asset paths, revisions and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and tools |
| [Environment configuration](environment/docker-compose.yaml) | Public read-only mounts and CPU quota |
| [Verifier](tests/) | Stage isolation, output validation and scoring |
| [Resource policy](environment/docs/available_resources.md) | Permitted APIs, models and credential handling |
| [Corpus license](ICSI_LICENSE.html) | Original terms and attribution |
| [SOURCES.md](SOURCES.md) | Dataset provenance, preparation and runtime asset sources |

## References

- [Data, model and method provenance](SOURCES.md).
