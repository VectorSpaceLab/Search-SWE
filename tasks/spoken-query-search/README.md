# Spoken-Query Document Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `spoken-query-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | SpokenMacroNDCG@10 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 19200 s |
| Dataset | SQuTR, six released corpora and four acoustic conditions |
| Public queries | 10 |
| Hidden queries | 4550 |

Retrieve documents from fixed, uncertain speech transcriptions and their alternatives.

### Overview

Speech recognition can mishear names and important query terms. This task
provides a best transcription, alternative hypotheses and confidence information
rather than clean question text. The system must use those inputs to retrieve
relevant documents.

The recognizer is fixed. Document indexing, uncertainty handling and ranked
retrieval belong to the submission.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | Six complete collections totaling 8,292,040 documents |
| `data/validation/` | Ten public rows from five original question families |
| `models/encoder/` | Local multilingual-e5-small weights and tokenizer |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs come from [SQuTR](https://github.com/ttoyekk1a/SQuTR-Spoken-Query-to-Text-Retrieval)
at dataset revision `2f1b041e2e98e0d28ed68fbcf22126ef247eb719`.
The original corpora and qrels are retained. Audio was synthesized from source
questions and mixed with noise; it is not natural human speech.

This task supplies fixed Whisper-small N-best transcriptions prepared without
clean question text or qrels as recognition inputs. Conditional token
probabilities are aggregated into hypothesis and word confidence information.
This recognizer differs from the systems evaluated in the source paper.

Five original families are public in clean and SNR20 conditions, giving ten
public rows. The private split has 4,550 rows across four acoustic conditions.
SNR0/SNR10 variants of the public families are unused. No question family crosses
the split. Here clean names an acoustic condition; clean reference text and audio
are not runtime inputs.

#### Fixed Components and Allowed Changes

Transcriptions, confidence fields, document collections and source relevance
labels are fixed. At most five retrieval formulations and 50 further
query-document reranking pairs are allowed per request. No new speech
recognition is available.

Indexing and ranking are implementation choices. No document or query vectors
or starter are supplied. Optional OpenRouter and Jina access follows the
[resource policy](environment/docs/available_resources.md).

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has two hours. Build has 10,800 seconds; each of four
query calls has 1,350 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Using transcription alternatives and confidence information.
- Retrieving across six complete multilingual document collections.
- Maintaining retrieval quality under different acoustic conditions.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Requests name a collection domain and provide the best
transcription and alternatives. Return up to ten distinct documents from that
domain, with finite nonincreasing scores.

Commands run as a non-root user with code and inputs read-only. Build writes
inside the supplied index directory, whose parent is not writable. The index
is read-only for query calls. Acoustic conditions are executed in separate
calls with fresh scratch; requests must be processed independently.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Compute original graded nDCG@10, average within each collection and acoustic
condition, then give the six collections and four conditions equal weight.


The split separates question families, but it is not an independently verified
speaker-disjoint benchmark. Per-condition and per-collection scores are reported
to show the effect of recognition noise.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.4530094614433184` and integer score anchor `a = 15` on the 0–100 scale:

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
`tasks/spoken-query-search/`:

```bash
python scripts/download_assets.py --task spoken-query-search
bash scripts/run_task.sh --task spoken-query-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/spoken-query-search/`.

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

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

- [Data, model and method provenance](SOURCES.md).
