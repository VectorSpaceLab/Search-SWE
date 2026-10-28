# Financial-Report Evidence Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `financial-report-qa` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | EvidenceRecall@5 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 12000 s |
| Dataset | DocFinQA full reports aligned with original FinQA gold_inds |
| Public queries | 5 |
| Hidden queries | 4236 |

Find the original report passages supporting financial questions over a shared annual-report collection.

### Overview

An analyst knows what figures need checking but may not know which report
contains them. The system must search a fixed collection and return the exact
original passages needed to verify each financial question.

The task evaluates evidence retrieval. It does not ask the submitted system
to calculate or generate a final financial answer.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/reports.jsonl` | 885 complete reports, totaling 470,982,872 bytes |
| `data/validation/queries.jsonl` | Five public financial questions |
| `data/validation/labels.jsonl` | Verified public evidence locations |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Report text and questions come from [DocFinQA](https://huggingface.co/datasets/kensho/DocFinQA).
Human support facts come from [FinQA](https://github.com/czyssrs/FinQA).
The upstream question pool yields 4,241 retained questions and 3,188 exclusions
after ambiguity and evidence-alignment checks. No new questions were generated.

Five question/evidence examples are public and 4,236 questions are held out.
All 885 reports remain public, including reports without retained evidence.
The 6,610 aligned support facts comprise seven public and 6,603 private units.
Equivalent repeated passages are alternative locations for the same fact.

#### Fixed Components and Allowed Changes

The reports, question/evidence split, passage interface and execution limits
are fixed. Document processing, index structure, retrieval and evidence
selection are implementation choices. No starter is supplied. Optional
OpenRouter and Jina services follow the
[resource policy](environment/docs/available_resources.md).

#### Environment and Resource Limits

The CPU environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and
no GPU. Development has two hours. Index construction has 1,800 seconds;
each of two query calls has 3,600 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Added reviewed alternative evidence locations for 18 held-out questions |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Searching across complete reports without a target document ID.
- Preserving original report identities and character positions.
- Covering all required evidence within a short passage budget.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` plus their supporting
files under `/app`. Queries contain only a query ID and question. Each output
contains up to five ranked evidence spans, with report ID and original Unicode
character offsets. Start is inclusive, end exclusive, and each span is at most
512 characters.

Submitted commands run as a non-root user with code and corpus read-only.
The supplied index directory stays writable across calls; its parent is not
writable. Generated data use the supplied index, output and temporary paths.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

For each question, EvidenceRecall@5 is the number of covered reference
evidence units divided by the number of required units. Average these recalls
equally over the 4,236 held-out questions.

A fact is covered when the union of returned spans in the correct report
completely covers at least one verified location for that fact. Partial overlap
is insufficient. Multiple hits on the same fact do not add credit. Several
facts can fit in one span, and adjacent spans can jointly cover a fact.

Evidence locations are aligned to complete FinQA support text and table
context, with checks on numeric values and formatting. They are not inferred
by searching for the expected final answer number.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.6831800740440966` and integer score anchor `a = 20` on the 0–100 scale:

```text
reward(q) = (a / 100) * q / b                             if 0 <= q <= b
            a / 100 + (1 - a / 100) * (q - b) / (1 - b)  if b < q <= 1
```

This maps raw quality 0, b and 1 to rewards 0, a / 100 and 1. Raw quality and
auxiliary diagnostics are reported separately. Harbor retains the 0–1 reward
precision; a displayed 0–100 score is rounded to one decimal place.
Correctness and trajectory-audit gates take precedence over this conversion.

#### Correctness and Resource Gates

The verifier checks successful index construction, executable behavior,
query IDs, span count, report IDs, Unicode offsets and the 512-character limit.
Duplicate output rows invalidate their query. Repeated evidence spans do not
increase recall. Completed valid JSONL rows remain usable after a query timeout;
missing or invalid query results score zero. A non-timeout query-command failure
invalidates that call.

#### Integrity Checks and Final Reward

A separate trajectory audit checks task compliance and gates the quality
reward. A confirmed violation sets reward to zero; unavailable or incomplete
audit results are not valid evidence of model quality. The audit uses pinned
RewardKit 0.2.0 with verifier-only OpenRouter settings.

Private questions, reference labels and audit credentials are excluded from
the agent environment and protected from submitted programs.

### Running This Task

Follow the repository [quick start](../../docs/quickstart.md) to prepare Harbor
and Docker, the [evaluation guide](../../docs/evaluation.md) for agent and
credential configuration, and the [asset guide](../../docs/assets.md) for
restoring fixed inputs.

Optional task APIs use `OPENROUTER_API_KEY` and `JINA_API_KEY` where the
resource policy permits them. Trajectory auditing uses the separate verifier
credential group `VERIFIER_OPENAI_*`.

The commands below apply in a checkout with this package installed at
`tasks/financial-report-qa/`:

```bash
python scripts/download_assets.py --task financial-report-qa
bash scripts/run_task.sh --task financial-report-qa --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/financial-report-qa/`.

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
