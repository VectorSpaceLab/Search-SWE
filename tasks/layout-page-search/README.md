# Visual-Document Evidence Page Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `layout-page-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | EvidencePageSetF1 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 12000 s |
| Dataset | MMLongBench-Doc original chart/figure/layout evidence annotations |
| Public queries | 5 |
| Hidden queries | 515 |

Find the complete set of supporting pages within a specified visual document.

### Overview

A question about a chart, figure or page layout may require more than one
page of evidence. The system must return a compact set of pages that together
support the question within the document named by the request.

The task evaluates page selection rather than answer generation. The document
is supplied in the query; it is not a collection-wide document-identification
task.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 5,294 rendered pages and extracted text from 119 documents |
| `data/validation/` | Five public questions and original evidence-page labels |
| `models/page-encoder/` | ColQwen2.5 adapter and processor |
| `models/vision-backbone/` | Compatible local retrieval backbone |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Questions and original evidence-page annotations come from MMLongBench-Doc
through the [DocLens dataset release](https://huggingface.co/datasets/dwzhu/DocLensDatasets).
Retained questions have chart, figure or generalized-text/layout evidence,
existing evidence pages and a complete reference page set within ten pages.

The resulting 520 unchanged questions are split into five public examples and
515 held-out questions. All 119 documents are shared. The source annotations
identify visual evidence, but do not certify that text-only retrieval must fail.
This task overlaps the document source used by
`visual-document-qa`; the output and metric differ.

#### Fixed Components and Allowed Changes

The corpus, specified document, evidence labels and output interface are fixed.
Supplied encoder weights remain fixed. An optional scoring or adaptation
component may have at most five million trainable parameters and use at most
45 minutes of training. At most 40 pages per query may receive query-dependent
token, region or learned pairwise comparisons.

Representations, index structure and page selection are implementation choices.
No precomputed vectors, starter or external API resource is supplied.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has six hours, including the optional adaptation
allowance. Build has 3,600 seconds; each of two query calls has 2,700 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Combining page text and visual evidence.
- Selecting a complete evidence set without adding unrelated pages.
- Managing page-level representations and query-dependent comparisons.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Return up to ten distinct page IDs from the specified document,
with finite nonincreasing scores. No answer text or bounding box is required.

Commands run as a non-root user with code and inputs read-only. The supplied
index directory remains writable across calls, while its parent is not writable.
Use the supplied index, output, cache and temporary paths for generated files.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

For each question, compute set F1 between the returned pages and the complete
original evidence-page set. Quality is mean F1 over 515 held-out questions.
 Domain means are diagnostic.

The set metric penalizes both missing evidence and extra pages. Returning the
complete annotated evidence set achieves full per-query credit. It does not
measure answer accuracy or bounding-box localization.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.5734305608092015` and integer score anchor `a = 20` on the 0–100 scale:

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

Prepare the GPU runtime and independent trajectory-audit credentials.
Submitted task programs run offline and receive no provider credentials.

The commands below apply in a checkout with this package installed at
`tasks/layout-page-search/`:

```bash
python scripts/download_assets.py --task layout-page-search
bash scripts/run_task.sh --task layout-page-search --gpu-device 0 --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/layout-page-search/`.

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
