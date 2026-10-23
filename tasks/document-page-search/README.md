# Multilingual Visual Document Page Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `document-page-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | DomainMacroNDCG@10 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 19200 s |
| Dataset | ViDoRe V3, eight public domains |
| Public queries | 30 |
| Hidden queries | 14484 |

Rank document pages for questions across several languages and document domains.

### Overview

Searching visual documents requires finding evidence in page images, tables
and text, including when the question and document use different languages.
This task indexes complete page collections and returns a ranked page list.

Each request names a domain. Search covers the full supplied page collection
for that domain; the target document and page are not given.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 19,252 page images, Markdown and page metadata |
| `data/validation/` | 30 public rows: five original questions in six languages |
| `models/page-encoder/` | ColQwen2.5 adapter and processor |
| `models/vision-backbone/` | Compatible local retrieval backbone |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs come from [ViDoRe V3](https://huggingface.co/collections/vidore/vidore-v3).
The task retains original page images, Markdown and graded relevance judgments
across eight domains and six question languages.

The five public question families give 30 input rows. The other 2,414 families
give 14,484 held-out rows. Translations of one question stay in the same split.
All page collections are shared by both splits.

#### Fixed Components and Allowed Changes

The collection, question domain, relevance labels and ranked-output interface
are fixed. Parsing, representations, index design and ranking are implementation
choices. Page and query embeddings are not supplied; the local ColQwen2.5
resources are optional. OpenRouter and Jina access follows the
[resource policy](environment/docs/available_resources.md). No starter is provided.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has two hours. Index construction has 10,800 seconds;
each of two query calls has 2,700 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Representing page text, images and layout for retrieval.
- Handling cross-language questions over a fixed page collection.
- Balancing indexing cost and ranking quality across eight domains.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with their supporting
files under `/app`. Each question produces up to ten distinct page IDs from
its requested domain, with finite nonincreasing scores. No answer or bounding
box is required.

The separate verifier runs commands as a non-root user with submission code
and inputs read-only. The supplied index directory remains writable across
calls; its parent is not writable. Output, cache and temporary files must use
the paths supplied to the command.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Compute nDCG@10 with the original graded relevance labels and linear gains.
Average query scores within each domain, then give the eight domains equal
weight. Missing or invalid query results remain in the denominator.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.5362634643282924` and integer score anchor `a = 20` on the 0–100 scale:

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
`tasks/document-page-search/`:

```bash
python scripts/download_assets.py --task document-page-search
bash scripts/run_task.sh --task document-page-search --gpu-device 0 --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/document-page-search/`.

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
