# Composed Image Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `composed-image-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | ComposedSourceQuality |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 36000 s |
| Dataset | CIRCO and CIRR original relative captions |
| Public queries | 5 |
| Hidden queries | 4392 |

Find matching gallery photographs from a reference image and a requested modification.

### Overview

A user can describe how an existing photograph should change without naming
every detail that should stay the same. The system must combine the reference
image and modification request, then rank photographs from a shared gallery.

The collection combines two sources with different relevance annotations:
CIRCO has multiple matching images per request, while CIRR supplies one target.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 125,226 gallery images and their image IDs |
| `data/validation/` | Five public requests and relevance labels |
| `models/clip/` | Local CLIP ViT-B/32 weights and processor |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

The shared gallery combines CIRCO with the official CIRR validation release.
There are five public requests (two CIRCO and three CIRR) and 4,392 held-out
requests (214 CIRCO and 4,178 CIRR). Query IDs are disjoint.

[CIRCO](https://github.com/miccunifi/CIRCO) supplies 216 original queries.
[CIRR](https://github.com/Cuberick-Orion/CIRR/tree/cirr_dataset/captions)
contributes 4,181 original captions and 2,297 images. Image IDs from the
[pinned CIRR image mirror](https://huggingface.co/datasets/royokong/cirr_imgs/tree/7a25e03bc7640ef61d80b854e3c9762871d74a28)
were matched to the official captions. Requests and relevance targets were not
generated for this task. CIRR requests have no shared-concept annotation.

#### Fixed Components and Allowed Changes

The gallery, requests and output interface are fixed. Index design, visual
representations, candidate selection and ranking are implementation choices.
No precomputed gallery or query vectors and no starter are supplied. Optional
OpenRouter and Jina calls follow the [resource policy](environment/docs/available_resources.md).
Additional query-dependent visual inspection is limited to 100 candidates.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has two hours; index construction has 3,600 seconds.
Two query calls each have an independent 14,400-second allowance.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Combining visual context with a natural-language modification.
- Preserving unchanged content while finding the requested difference.
- Indexing a large image gallery within GPU and execution budgets.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Build once from the gallery, then accept repeated query files.
Each result contains the query ID and up to 50 distinct ranked image IDs with
finite scores. The reference image must be excluded.

Verification runs the submitted commands as a non-root user with code and
inputs read-only. The supplied index directory stays writable across calls;
its parent is not writable. Generated files must use the index, output and
temporary paths supplied to each stage.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

For CIRCO, quality is the mean of AP@5, AP@10, AP@25 and AP@50.
For CIRR, it is the mean of Recall@1, Recall@5, Recall@10 and Recall@50.
Queries are averaged within each source, then the two source scores receive
equal weight.

The source metrics retain their original positive labels. The shared gallery
and equal weighting of the two sources are this task's adaptation; unlabeled
alternatives are not treated as newly certified negatives.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.26812065144613684` and integer score anchor `a = 20` on the 0–100 scale:

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
`tasks/composed-image-search/`:

```bash
python scripts/download_assets.py --task composed-image-search
bash scripts/run_task.sh --task composed-image-search --gpu-device 0 --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/composed-image-search/`.

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
