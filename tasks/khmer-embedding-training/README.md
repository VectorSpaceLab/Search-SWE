# Khmer-to-English Embedding Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `khmer-embedding-training` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | Recall@100 |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 48000 s |
| Dataset | MKQA Khmer / BEIR NQ |
| Public queries | 3 |
| Hidden queries | 1000 |

Adapt a supplied embedding backbone and retrieve English documents for Khmer questions.

### Overview

Cross-language retrieval must connect a Khmer question to an English
document even when they share no words. This task supplies a large English
collection, a multilingual embedding backbone and three examples.

Development can use an additional local generative model. That model is absent
from evaluation, where the trained embedding checkpoint and submitted search
pipeline must operate offline.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.parquet` | 2,681,468 English documents |
| `data/examples.jsonl` | Three Khmer questions with English answer aliases |
| `models/multilingual-e5-large/` | Embedding backbone |
| `models/Qwen3.5-9B/` | Optional development-only local generative model |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

The collection is [BEIR/NQ](https://huggingface.co/datasets/BeIR/nq).
Question and answer aliases originate from filtered MKQA records checked
against the original data. The question pool contains three public examples,
1,000 held-out questions and 5,616 unused questions.

The supplied backbone is intfloat/multilingual-e5-large, and the optional
generative checkpoint is Qwen/Qwen3.5-9B. Upstream model revisions and restored
files are recorded in [assets.json](assets.json). No extra labeled training
questions are supplied.

#### Fixed Components and Allowed Changes

The embedding backbone architecture, parameter names and shapes, configuration
and tokenizer are fixed. Its weights are trainable. Training-data preparation,
index structure and the retrieval implementation are submission choices.
No starter is supplied, and no external API or network resource is available.

The optional generative model is a development resource. Neither it nor an
already built corpus index is transferred as a runtime retrieval resource.

#### Environment and Resource Limits

Development has six hours with eight CPU cores, 32 GiB RAM, 100 GiB storage
and one A100 40 GiB GPU. The verifier provides the same CPU, RAM and GPU
resources without the development-only generative model.
Index construction has 43,200 seconds; each of two query calls has 1,800 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Adapting cross-language representations with limited labeled examples.
- Building a reusable index over 2,681,468 documents.
- Packaging an offline checkpoint and deterministic ranked retrieval.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh`, `/app/run.sh` and the trained checkpoint
under `/app/submission/model/`, including `model.safetensors`, `config.json`
and unchanged tokenizer files. The checkpoint must load locally with standard
Hugging Face AutoModel and AutoTokenizer and without remote code.

Build creates a fresh collection index before evaluation queries are exposed.
Each query returns 100 unique zero-based corpus positions and finite scores,
ordered by decreasing score and then increasing corpus position for ties.
Build and retrieval run under separate non-root roles with read-only code and
inputs. Unlike the other tasks, the index directory initially does not exist;
its parent is writable. After construction, retrieval sees a read-only index.

The full commands and output contract are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Recall@100 uses the source answer-token hit rule: a question succeeds when
at least one of the first 100 retrieved documents contains an accepted answer.
Recall@20 is diagnostic.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.595` and integer score anchor `a = 15` on the 0–100 scale:

```text
reward(q) = (a / 100) * q / b                             if 0 <= q <= b
            a / 100 + (1 - a / 100) * (q - b) / (1 - b)  if b < q <= 1
```

This maps raw quality 0, b and 1 to rewards 0, a / 100 and 1. Raw quality and
auxiliary diagnostics are reported separately. Harbor retains the 0–1 reward
precision; a displayed 0–100 score is rounded to one decimal place.
Correctness and trajectory-audit gates take precedence over this conversion.

#### Correctness and Resource Gates

The verifier checks local checkpoint loading, preserved architecture and
tokenizer, a successful fresh build, complete query coverage, 100 valid unique
positions per query, finite sorted scores and time limits. Hidden questions,
answer aliases, the generative model and judge credentials are unavailable
to submitted build and retrieval processes.

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
`tasks/khmer-embedding-training/`:

```bash
python scripts/download_assets.py --task khmer-embedding-training
bash scripts/run_task.sh --task khmer-embedding-training --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Adjust `--model` and `--reasoning-effort` for another supported model.
Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/khmer-embedding-training/`.

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
