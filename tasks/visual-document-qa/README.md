# Visual-Document Question Answering

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `visual-document-qa` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | SourceMacroAnswerAccuracy |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 45000 s |
| Dataset | DocLensDatasets: MMLongBench-Doc and FinRAGBench-V |
| Public queries | 5 |
| Hidden queries | 2471 |

Answer questions from text, tables and figures in a specified long document.

### Overview

Relevant information in a long PDF may span prose, tables, charts and
several pages. The system must locate and read that evidence, then give a direct
answer or identify that the document does not contain the requested information.

Each request identifies a document. Evidence-page citations are reported, while
final answer quality is the primary metric.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 433 original PDFs, per-page extracted text and document metadata |
| `data/validation/` | Five public questions, answers and page references |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs use MMLongBench-Doc and FinRAGBench-V from
[DocLensDatasets](https://huggingface.co/datasets/dwzhu/DocLensDatasets/tree/7a54da77adf09d2c88c67f1bbb725718260f1dc1),
with evaluation adapted from [DocLens](https://github.com/dwzhu-pku/DocLens)
as described below. The shared collection contains 433 PDFs and 29,149 pages.

There are five public and 2,471 held-out questions. Identical source PDFs are
shared rather than duplicated, and documents associated with public examples
can also appear in private questions. Four upstream answer-type metadata fields
are corrected deterministically; the questions and canonical answers are unchanged.
Text, list and unanswerable answers use semantic comparison.

#### Fixed Components and Allowed Changes

PDFs, original question/answer labels and output interfaces are fixed.
Parsing, rendering, indexing, retrieval and answer synthesis are implementation
choices. No starter, local GPU or precomputed vectors are supplied.
Optional OpenRouter and Jina resources follow the
[resource policy](environment/docs/available_resources.md).

#### Environment and Resource Limits

The CPU environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and
no GPU. Development has two hours. Build has 14,400 seconds; each of two
query calls has an independent 10,800-second allowance. These limits remain
inside the 45,000-second overall verifier budget.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Judge MMLongBench-Doc text, list and unanswerable answers by semantic correctness |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Indexing long PDFs while retaining page provenance.
- Combining textual and visual evidence for answer generation.
- Handling numeric, list and unanswerable questions.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Each input names a document and question. Return the query ID,
a natural-language answer and the one-based supporting page numbers.
Use an empty page list when no supporting page exists.

Submitted commands run as a non-root user with code and inputs read-only.
The supplied index directory stays writable across calls; its parent is not
writable. Generated files must use the supplied index, output and temporary paths.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

MMLongBench-Doc integer and float answers use the source answer-extraction
prompt and numeric comparators. Text, list and unanswerable answers receive
a binary semantic judgment directly from the question, reference and full
submitted answer. Equivalent wording receives credit;
incorrect entities, comparisons, missing list items or unsupported claims do
not. Each semantic judgment records a short reason.
FinRAGBench-V uses its original binary answer judge. Trusted model calls use
`google/gemini-2.5-flash` through OpenRouter.

Average answers within each source, then give the two sources equal weight.

Evidence-page precision, recall and F1 are diagnostics, not part of the primary
answer score. Out-of-range source page references are excluded only from citation
diagnostics and do not remove the corresponding answer question.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.4350989780543772` and integer score anchor `a = 20` on the 0–100 scale:

```text
reward(q) = (a / 100) * q / b                             if 0 <= q <= b
            a / 100 + (1 - a / 100) * (q - b) / (1 - b)  if b < q <= 1
```

This maps raw quality 0, b and 1 to rewards 0, a / 100 and 1. Raw quality and
auxiliary diagnostics are reported separately. Harbor retains the 0–1 reward
precision; a displayed 0–100 score is rounded to one decimal place.
Correctness and trajectory-audit gates take precedence over this conversion.

#### Correctness and Resource Gates

The verifier checks execution, output structure, document/page validity and
stage limits. Completed valid rows survive query-call timeout; missing or invalid
rows receive zero. Other query-command failures invalidate that call.
Trusted answer-extraction or judge transport failures invalidate the measurement
rather than establishing a low baseline or model score.

#### Integrity Checks and Final Reward

A separate trajectory audit checks task compliance and gates the quality
reward. A confirmed violation sets reward to zero; unavailable or incomplete
audit results are not valid evidence of model quality. The audit uses pinned
RewardKit 0.2.0 with verifier-only OpenRouter settings.

Private questions, reference labels and audit credentials are excluded from
the agent environment and protected from submitted programs. Answer judges,
where used, are distinct from trajectory auditing.

### Running This Task

Follow the repository [quick start](../../docs/quickstart.md) to prepare Harbor
and Docker, the [evaluation guide](../../docs/evaluation.md) for agent and
credential configuration, and the [asset guide](../../docs/assets.md) for
restoring fixed inputs.

Optional task APIs use `OPENROUTER_API_KEY` and `JINA_API_KEY` where the
resource policy permits them. Trajectory auditing uses the separate verifier
credential group `VERIFIER_OPENAI_*`.

Answer extraction and answer judging additionally require the verifier's
configured `DOCUMENT_JUDGE_MODEL` and its protected provider credential.
Submission API permission does not grant access to trusted judge settings.

The commands below apply in a checkout with this package installed at
`tasks/visual-document-qa/`:

```bash
python scripts/download_assets.py --task visual-document-qa
bash scripts/run_task.sh --task visual-document-qa --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/visual-document-qa/`.

### Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [raw-instruction.md](raw-instruction.md) | Structured authoring source, excluded from agent mounts |
| [task.toml](task.toml) | Task identity, collected artifacts, resources and phase budgets |
| [assets.json](assets.json) | Restored asset paths, available source revisions and checksums |
| [environment/docs/environment.md](environment/docs/environment.md) | Installed runtime and tools |
| [environment/docker-compose.yaml](environment/docker-compose.yaml) | Public read-only mounts and hardware requests |
| [tests/](tests/) | Execution, output validation, isolation and scoring |
| [environment/docs/available_resources.md](environment/docs/available_resources.md) | Permitted APIs, models and credential handling |
| [SOURCES.md](SOURCES.md) | Dataset provenance, preparation and runtime asset sources |

## References

- [Data, model and method provenance](SOURCES.md).
