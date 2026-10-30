# Video-Moment Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `video-moment-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | SourceMacroGridUtility |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 12000 s |
| Dataset | Charades-STA and ActivityNet Captions, pinned Lighthouse feature release |
| Public queries | 5 |
| Hidden queries | 450 |

Locate the time interval matching a natural-language description within a specified video.

### Overview

Searching within a video requires finding both the right event and its time
boundaries. Each request names a video and an original description. The system
returns one interval on the video's supplied time grid.

The task uses released frame features and local encoder weights, rather than
raw videos or precomputed query representations.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | Released features, time grids and metadata for 742 videos |
| `data/training/` | 902 original training queries and interval labels |
| `data/validation/` | Five public evaluation queries and interval labels |
| `models/clip/` | Fixed CLIP ViT-B/32 weights matching the released features |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Annotations come from Charades-STA and ActivityNet Captions through the
[pinned Lighthouse release](https://github.com/line/lighthouse/tree/3e841d3d662c8440afed514908566fed2d5e82a7).
The final split contains 902 training, five public and 450 held-out queries.
Training videos are separate from evaluation videos; public and private
evaluation questions share the evaluation corpus.

Source-video families with inconsistent feature coverage or a zero-length source
interval are excluded without creating replacement labels. Retained descriptions
and intervals are otherwise unchanged. The final endpoint of each time grid is
the source duration. Slight source endpoint discrepancies are handled by the
grid-attainable metric below.

This supervised adaptation differs from the weak-supervision setting of the
seed paper. Raw videos, generated query vectors and tokenized descriptions
are not supplied.

#### Fixed Components and Allowed Changes

Video features, time grids and local encoders are fixed. An optional
temporal/scoring component may have at most five million trainable parameters
and use at most 45 minutes of training. At most 64 candidate intervals per
request may receive learned or token-level fine scoring. Cheap frame screening
and boundary proposals remain allowed.

Indexing and interval selection are implementation choices. No starter or
external API resource is supplied.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has six hours, including the optional training allowance.
Build has 3,600 seconds; each of two query calls has 2,700 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Matching descriptions to temporal evidence in fixed video features.
- Choosing accurate start and end boundaries.
- Using labeled intervals within a bounded adaptation budget.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting files
under `/app`. Each request produces one nonempty start/end interval whose
endpoints belong to the specified video's grid.

Commands run as a non-root user with code and inputs read-only. Build writes
inside the supplied index directory, whose parent is not writable. Retrieval
sees the completed index read-only and uses fresh output and temporary paths.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Let x be the best IoU between the predicted interval and the original
acceptable intervals. Its utility is:

```text
u(x) = 0.7 * mean(I[x >= 0.5], I[x >= 0.7], I[x >= 0.9]) + 0.3 * x
```

Divide each query's utility by the best utility attainable with one legal
interval on its supplied grid. Average within each source, then give the two
sources equal weight.

Grid-optimal witnesses remain verifier-only. Invalid, reversed, missing,
nonfinite or non-grid intervals score zero. The grid correction accounts for
boundary precision limits; a long interval still loses IoU when it includes
unrelated time.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.14696558206208937` and integer score anchor `a = 15` on the 0–100 scale:

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
query IDs, finite start/end values, interval order, grid endpoints and stage
limits. Completed valid JSONL rows remain usable after a query timeout;
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

Prepare the GPU runtime and independent trajectory-audit credentials.
Submitted task programs run offline and receive no provider credentials.

The commands below apply in a checkout with this package installed at
`tasks/video-moment-search/`:

```bash
python scripts/download_assets.py --task video-moment-search
bash scripts/run_task.sh --task video-moment-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/video-moment-search/`.

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
