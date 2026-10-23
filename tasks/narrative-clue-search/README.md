# Narrative-Clue Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `narrative-clue-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | QueryMeanNDCG@10 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 12000 s |
| Dataset | TREC ToT 2023 |
| Public queries | 5 |
| Hidden queries | 445 |

Find a work from a user's long, incomplete and uncertain recollection.

### Overview

A user may remember a film through scattered plot details, comparisons and
uncertain impressions rather than its title. The system must search article
text and return the matching work near the start of its ranking.

This task uses human recollections and their released relevance judgments.
It leaves query interpretation and retrieval design to the implementation.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/records.jsonl` | 231,824 nonempty articles with unambiguous IDs |
| `data/validation/` | Five public recollections and qrels |
| `data/training/sentence_labels.jsonl` | Original sentence annotations for public queries only |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs use the [TREC Tip-of-the-Tongue 2023 movie collection](https://trec-tot.github.io/guidelines-2023).
The [official 2024 dev2 release](https://trec-tot.github.io/guidelines-2024)
republishes the 2023 test judgments used here.

All 450 original questions are retained: five public and 445 held out.
The 231,852-row source archive contains 26 empty-text entries and two articles
with the same ID; these 28 entries are removed, with all relevance targets
verified unaffected. Questions retain their original recollections but omit
target links and answer metadata. Public sentence annotations add no hidden-query
supervision.

#### Fixed Components and Allowed Changes

The article collection, questions, relevance labels and ranked-output interface
are fixed. Index design, query formulations, candidate selection and ranking
are implementation choices. There is no required BM25 pipeline, fixed rewrite
count or ban on semantic reranking. Optional OpenRouter and Jina services follow
the [resource policy](environment/docs/available_resources.md). No starter is supplied.

#### Environment and Resource Limits

The CPU environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and
no GPU. Development has two hours. Index construction has 3,600 seconds;
each of two query calls has 2,700 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Extracting useful retrieval evidence from a long recollection.
- Handling uncertain or incorrect remembered details.
- Ranking works from a full article collection.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Each request contains the query ID and recollection text.
Return up to ten distinct article IDs with finite nonincreasing scores.

Commands run as a non-root user with code and corpus read-only. The supplied
index directory stays writable across calls; its parent is not writable.
Use the supplied index, output, cache and temporary paths for generated files.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Compute nDCG@10 using complete original qrels, then average equally over
445 held-out questions.

Four category means based on original human uncertainty annotations and a fixed
median narrative length are diagnostics. They do not change query weights or
introduce model-generated categories.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.40178618363049623` and integer score anchor `a = 20` on the 0–100 scale:

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
query coverage, IDs, duplicate handling, finite scores and stage limits.
Completed valid JSONL rows remain usable after a query timeout; missing or
invalid rows score zero. A non-timeout query-command failure invalidates
that call. See [instruction.md](instruction.md) and the verifier for the exact
task-specific validity checks.

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
`tasks/narrative-clue-search/`:

```bash
python scripts/download_assets.py --task narrative-clue-search
bash scripts/run_task.sh --task narrative-clue-search --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/narrative-clue-search/`.

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
