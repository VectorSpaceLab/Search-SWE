# Same-Place Image Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `same-place-image-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | HardPlaceMacroNDCG@5 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 7200 s / 12000 s |
| Dataset | Revisited Oxford and Paris, released expert ground truth |
| Public queries | 5 |
| Hidden queries | 135 |

Retrieve photographs of the same physical building across viewpoints, scale and occlusion.

### Overview

A cropped photograph may show only part of a building. The system must find
other views of that physical place rather than buildings with similar style.
Each request includes gallery image IDs that are excluded from its ranking.

The scope is retrieval within the supplied landmark galleries. The task does
not ask for web geolocation or external webpage evidence.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 11,315 original gallery photographs and IDs |
| `data/queries/` | Public query crops |
| `data/validation/` | Five public queries with relevance labels |
| `models/clip/` | Local fixed CLIP ViT-B/32 weights and processor |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Source labels use the [Revisited Oxford/Paris Hard protocol](https://github.com/filipradenovic/revisitop),
with the source [Oxford](https://www.robots.ox.ac.uk/~vgg/data/oxbuildings/) and
[Paris](https://www.robots.ox.ac.uk/~vgg/data/parisbuildings/) image releases.
Of 140 query crops, five are public and 135 are held out. The gallery is shared.

Original Hard positives are retained. Original Easy and Junk images are
per-query exclusions, not relabeled negatives. Exact decoded duplicates of
query-source images are excluded from the gallery. No GPS-derived or generated
same-place labels are added. The limited landmark families do not establish
worldwide geographic generalization.

#### Fixed Components and Allowed Changes

The gallery, query crops, Hard labels and output interface are fixed.
CLIP weights remain fixed. Index structure, global and local representations
and ranking are implementation choices; no precomputed vectors or starter
are supplied. Additional pixel-based geometric verification may examine at
most 20 candidates per request. External APIs are unavailable.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has two hours. Index construction has 3,600 seconds;
each of two query calls has 2,700 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Matching physical identity across different views and image crops.
- Combining gallery indexing and bounded local visual verification.
- Respecting per-query exclusions and the source relevance protocol.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with their supporting
files under `/app`. For each cropped image and exclusion list, return up to
five distinct eligible gallery IDs with finite nonincreasing scores.

Commands run as a non-root user with code and inputs read-only. The supplied
index directory is writable during build, while its parent is not writable.
The completed index is read-only during retrieval. Query outputs and caches
use the supplied writable output and temporary paths.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Compute binary nDCG@5 against the original Hard positives after removing
excluded images. Average within Oxford and Paris, then give the two sources
equal weight.

This task uses the source Hard relevance protocol with a task-specific top-five
metric. Invalid or excluded returned IDs invalidate that query.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.5364309790092764` and integer score anchor `a = 15` on the 0–100 scale:

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
`tasks/same-place-image-search/`:

```bash
python scripts/download_assets.py --task same-place-image-search
bash scripts/run_task.sh --task same-place-image-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/same-place-image-search/`.

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
