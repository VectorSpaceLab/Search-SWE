# Sketch-and-Text Image Search

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `sketch-text-search` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | LevelMacroRecallMRR@3 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 12000 s |
| Dataset | CIRThan with a deterministic partial-sketch input condition |
| Public queries | 15 |
| Hidden queries | 1242 |

Retrieve an artwork from a partial sketch and its written description.

### Overview

A rough sketch may omit parts of the desired scene. The system must combine
the visible drawing and description to locate the target artwork.

The collection retains three description levels. Each sketch-description pair
is processed independently; descriptions for other requests are not extra
query context.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/` | 2,287 gallery artworks and image IDs |
| `data/queries/` | Public partial-sketch images |
| `data/training/` | 5,604 original training queries and labels |
| `data/validation/` | 15 public rows: five query families at three description levels |
| `models/clip/` | Local fixed CLIP ViT-B/32 weights and processor |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs derive from [CIRThan](https://github.com/jinyuxu-whut/CIRThan/tree/b1499eb9393b12f1499a983f8fedfe7d14869024).
The original descriptions, targets and training families are retained.
Five evaluation families are public and 414 are held out, giving 15 public and
1,242 held-out rows. Description levels of one family do not cross the split.

The sketch input is an explicit task adaptation: a deterministic left or right
60 percent of each original sketch is retained in its coordinate frame, and
the remaining 40 percent is masked. Selection uses only the opaque sketch ID.
Complete original sketches are not supplied. This is a partial-sketch task,
not a claim to reproduce the original paper's input condition.

#### Fixed Components and Allowed Changes

The gallery, partial sketches, description levels and output interface are
fixed. Supplied encoders remain fixed; optional scoring or fusion components
may use up to 30 minutes of adaptation. Indexing and ranking are implementation
choices. No precomputed vectors, starter or external APIs are supplied.

#### Environment and Resource Limits

The environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and one
40 GiB GPU. Development has six hours, including the adaptation allowance.
Build has 3,600 seconds. Each of three query calls, one per description level,
has 1,800 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Combining partial visual structure with text descriptions.
- Adapting scoring or fusion from supplied labeled examples.
- Maintaining quality across broad and detailed descriptions.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh` and `/app/run.sh` with supporting code and
learned files under `/app`. Each request contains a sketch path and description;
return up to ten distinct gallery IDs with finite nonincreasing scores.

Commands run as a non-root user with code and inputs read-only. The supplied
index directory is writable during build, but its parent is not writable.
Retrieval sees a read-only index and uses the supplied writable output and
temporary paths. A development-only permissions helper is available at
`/task/docs/check_runtime.py`; it performs no scoring.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Per-query quality is `0.5 × Recall@3 + 0.5 × MRR@3`.
Average within each of the three description levels, then give the levels
equal weight.

Up to ten results are accepted by the interface, but only the first three
affect the metric. The composite and partial-sketch input are task adaptations;
they do not reproduce the source paper's reported scores.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.32306763285024154` and integer score anchor `a = 15` on the 0–100 scale:

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
`tasks/sketch-text-search/`:

```bash
python scripts/download_assets.py --task sketch-text-search
bash scripts/run_task.sh --task sketch-text-search --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/sketch-text-search/`.

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
| [environment/docs/check_runtime.py](environment/docs/check_runtime.py) | Development-only check of build and query filesystem permissions |
| [SOURCES.md](SOURCES.md) | Dataset provenance, preparation and runtime asset sources |

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

- [Data, model and method provenance](SOURCES.md).
