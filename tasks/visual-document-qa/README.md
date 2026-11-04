# Visual-Document Question Answering

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `visual-document-qa` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | SourceMacroAnswerAccuracy |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 59400 s |
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
inside the 59,400-second overall verifier budget.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Judge MMLongBench-Doc text, list and unanswerable answers by semantic correctness |
| 2026-11-04 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Indexing long PDFs while retaining page provenance.
- Combining textual and visual evidence for answer generation.
- Handling numeric, list and unanswerable questions.

## Verification Explanation

Author-side regressions are in `authoring/tests/` and are excluded from the verifier image. Run `python -m unittest discover -s tasks/visual-document-qa/authoring/tests -p 'test_*.py'` from the repository root. Container-specific cases require a disposable verifier environment.

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
FinRAGBench-V uses its original binary answer-judging prompt. Trusted model calls use `deepseek/deepseek-v4.1-flash-1017` through OpenRouter, with reasoning disabled and a 512-token output limit for the concise extraction or judgment. Routing requires support for the requested parameters; truncated outputs are retried and invalidate the measurement if retries are exhausted. Semantic judgments use `score`/`reason`; FinRAGBench-V uses `score`/`analysis`, matching its prompt. Each answer is judged three times and the results are averaged before source aggregation.

Answer judging runs up to 32 questions concurrently, with each question's three calls kept sequential. Maintainers can set the positive integer `JUDGE_MAX_CONCURRENCY` before launching the verifier to adjust this limit. Higher concurrency does not reduce the request count, and its latency and error-rate effects depend on provider capacity.

Requests first use three local attempts with exponential backoff and jitter. Connection failures, timeouts, HTTP 408/429/5xx and temporary HTTP 402 responses with a valid `Retry-After` remain recoverable after those attempts: unfinished questions are deferred for 60/120/240/300 seconds plus jitter and retried within the existing verifier time budget. Workers share a cooldown, including the server's `Retry-After`, to pause new traffic during an outage. Credential/configuration errors stop promptly; persistently invalid judgments also require correction. No missing judgment is converted to an incorrect answer or omitted from the denominator.

Each successful sample, including score 0, is atomically saved under the protected verifier logs before the next sample starts. Checkpoints bind the model, judge code/prompts, evaluation data, submitted answer and sample index; changing the grading context cannot silently reuse older judgments. The verifier records concurrency, judging duration, deferred jobs and saved-sample counts. Normal execution stops scheduling before its 57,600-second process timeout, leaving time to save the failure report and stop outstanding requests. A persistent outage leaves an incomplete measurement with its saved progress.

Within the same trusted verifier trial, maintainers can resume the frozen answers after restoring service or restarting the judge process:

```bash
/opt/conda/bin/python /tests/grader.py --resume-judging
```

This command requires the original protected log directory and matching evaluation data/judge configuration. It skips build and answer generation, reuses saved samples, and allows up to six hours for the missing judgments. It updates `evaluation.json`; it does not rerun the independent trajectory audit or finalize the overall reward. Retain the original submission and audit artifacts when completing that trial. Deleting the trial logs also deletes its recovery state.

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

The score-mapping anchor is a fixed task-design parameter. This package does not include a baseline measurement record tied to the current semantic answer-grading revision. Revalidate the anchor against that revision before claiming that it remains empirically calibrated.

#### Correctness and Resource Gates

The verifier checks execution, output structure, document/page validity and
stage limits. Completed valid rows survive query-call timeout; missing or invalid
rows receive zero. Other query-command failures invalidate that call.
Unrecovered answer-extraction or judge failures leave the measurement incomplete, with completed samples retained for recovery, rather than establishing a low baseline or model score.

#### Integrity Checks and Final Reward

A separate trajectory audit checks task compliance and gates the quality
reward. A confirmed violation sets reward to zero; unavailable or incomplete
audit results are not valid evidence of model quality. The audit uses pinned
RewardKit 0.2.0 with verifier-only OpenRouter settings.

Private questions, reference labels and audit credentials are excluded from
the agent environment and protected from submitted programs. Answer judges,
where used, are distinct from trajectory auditing.

### Running This Task

Follow the repository [quick start](../../docs/evaluation/quickstart.md) to prepare Harbor
and Docker, the [evaluation guide](../../docs/evaluation/runtime.md) for agent and
credential configuration, and the [asset guide](../../docs/evaluation/assets.md) for
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
python scripts/assets/download_assets.py --task visual-document-qa
bash scripts/evaluation/run_task.sh --task visual-document-qa --agent codex --openrouter \
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

### Repeated verifier measurements

The submitted answer is held fixed while its source-specific answer evaluation runs three times. This includes the LLM extraction step for numeric answers, whose output can vary; its deterministic numeric comparator is applied to each extracted value. Semantic and FinRAG binary judgments are likewise averaged arithmetically, without majority voting. Citation diagnostics run once and source weighting and final score mapping stay unchanged. Any failed trusted call invalidates the measurement; transport retries are not independent votes. The primary supervisor allows 57,600 seconds (14,400 build + 21,600 query execution + 21,600 answer judging/setup); the overall verifier allows 59,400 seconds including the unchanged 1,200-second integrity audit and finalization. This triples the former answer-judging allowance; an unavailable/slow service can still exhaust it and invalidate the run.

## References

- [Data, model and method provenance](SOURCES.md).
