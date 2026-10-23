# Query-side Encoder Alignment

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `query-encoder-alignment` |
| Version | 1.0.0 |
| Authors | Search-SWE |
| Primary metric | Accuracy@1 error reduction above frozen 0.6B ridge, after runtime gate |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 5700 s |
| Dataset | local frozen retrieval corpus |
| Public queries | 100 |
| Hidden queries | 100 |

Improve a compact query encoder against a document collection whose embeddings cannot change.

### Overview

Replacing or tuning a query encoder does not automatically preserve its
compatibility with an existing document index. This task fixes the document
embeddings and asks the agent to improve retrieval from the query side using
the supplied Qwen3-Embedding-0.6B backbone.

The system must be accurate and materially faster than a larger teacher-side
reference. It is therefore a joint representation and execution problem:
a query vector must land in the right document space, and the complete query
pipeline must stay within the relative runtime budget.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/doc.npy` | 8,674 fixed float32 document vectors, each 2,560-dimensional |
| `data/corpus.jsonl` | The document identities corresponding to vector rows |
| `data/validation/` | 100 public queries and labels |
| `models/Qwen3-Embedding-0.6B/` | The required query-side backbone |
| `environment/starter/` | 4B time reference runner and validation notes |
| `environment/quality_baseline/` | Frozen 0.6B ridge baseline, fit/inference code and configuration |

The manifest also restores the Qwen3-Embedding-4B reference assets.
The development root user can read the 4B reference, including for teacher
signals on public inputs. Its private permissions keep it inaccessible to the
unprivileged final process; it is not an allowed final inference backbone.
There are 100 hidden evaluation queries, isolated from the agent environment.

#### Fixed Components and Allowed Changes

The query-side system may be adapted within the supplied 0.6B backbone
requirement. Document vectors must not be modified, re-encoded, replaced,
or reordered. Task network access during development is restricted to
`openrouter.ai` and `api.jina.ai`. Do not acquire replacement backbones,
evaluation labels, or external retrieval results. The final submission must
be self-contained and offline.

#### Environment and Resource Limits

The Python 3.12 runtime uses CUDA-enabled PyTorch, 8 CPUs, 32 GiB memory, and
a 100 GiB storage budget. The local Docker backend does not enforce that budget
with a filesystem quota; the completed calibration stayed well below it.
Both Compose configurations and `task.toml` request **one
NVIDIA GPU**. Use `--gpu-device <index-or-UUID>` to select the same host GPU for both phases.

The agent has 6 hours. Task-specific verification has 70 minutes inside
the 95-minute Harbor verifier phase, with the integrity check bounded separately.
The candidate must finish within **60% of the measured reference runtime**.
The evaluation runner also caps each reference/candidate run at 1,800 seconds.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Aligning a compact query representation with a frozen document-vector space.
- Preserving document identities and vector-row correspondence.
- Balancing query encoding quality with end-to-end execution time.
- Packaging deterministic inference and retrieval for offline verification.

## Verification Explanation

### Submission Contract

The complete deliverable lives under `/app/submission` and includes an executable
`run.sh`. It accepts document vectors and query files, and returns one ranked
document per query. The verifier copies only this directory.

Outputs must be deterministic and preserve query order, and execution must
leave no background processes. [instruction.md](instruction.md) defines the
complete interface; no separate submitted build step is required.

### Evaluation

#### Search Quality

The public quality reference freezes Qwen3-Embedding-0.6B and fits centered
ridge once on all public corpus/text-vector pairs. Its fixed settings and
reproduction commands are in [the baseline README](environment/quality_baseline/README.md).
The verifier independently fits the same version and measures A0 on the same
hidden queries and vectors. It never trains on hidden queries or labels.

```text
quality = clip((candidate Accuracy@1 - A0) / (1 - A0), 0, 1)
reward = quality if all gates pass else 0
score = 100 * reward
```

A reference failure or A0=1 is an invalid benchmark measurement, not a
candidate zero. Quality baseline configuration is frozen before hidden
measurement or model evaluation. The separate 4B reference supplies time only;
its accuracy is retained as a diagnostic. The old unmeasured 0.31 anchor is
removed. Raw candidate accuracy, A0, quality, runtime gate, judge health and
final reward are recorded separately.

Both references exclude same-ID documents and all canonical-text copies:
NFKC, collapse whitespace, casefold. They rank all unchanged vectors, filter,
then refill; ties use corpus row order. The grader rejects excluded results.

#### Correctness and Resource Gates

Candidate wall time must be at most `0.60 × starter wall time`, measured on the
same hidden workload. Missing the gate makes reward zero even if accuracy is
high. Timing is external and monotonic, including process/import/model/vector
loading, query encoding, search, output and exit. No warmup or file-cache flush;
run quality reference, time reference, then candidate. The first candidate run
sets time and a second fresh process checks byte-identical results. Timeout
cleanup time is logged separately. Vector checksums and shape, query coverage/order, result validity, and
clean process termination are also checked.

#### Integrity Checks and Final Reward

The normalized quality reward is accepted only after runtime and validity gates
and the independent trajectory audit pass. Failure at any gate produces zero.
Judge failures are marked `measurement_valid=false`, not reported as evidence
of model difficulty. Submitted processes run as UID 10001 with no credentials,
read-only runtime, protected reference/log directories and inherited seccomp
network denial.
The audit uses `deepseek/deepseek-v4.1-flash` via OpenRouter through pinned RewardKit 0.2.0 with
verifier-only DeepSeek endpoint and key settings.

### Running This Task

From the repository root, follow the [quick start](../../docs/quickstart.md)
to install the pinned Harbor dependencies and prepare Docker. Use the
[evaluation guide](../../docs/evaluation.md) to configure the selected agent and
task credential profile. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Prepare the GPU runtime and configure the independent integrity judge. Download
as a host user distinct from submission UID 10001, following the asset guide,
so the reference model's private file permissions retain their intended effect.

```bash
python scripts/download_assets.py --task query-encoder-alignment
python scripts/download_assets.py --task query-encoder-alignment --verify-only
bash scripts/run_task.sh --task query-encoder-alignment --gpu-device 0 --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --output jobs/query-encoder-alignment-UNIQUE_RUN_ID
```

The shared launcher defaults to Codex, also supports Pi and Claude Code, and
writes results under `jobs/query-encoder-alignment/`.
Configure `AGENT_OPENROUTER_API_KEY`, `VERIFIER_OPENAI_API_KEY` and
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` in the ignored repository
`.env`. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

### Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [task.toml](task.toml) | Task identity, artifact collection, and phase budgets |
| [assets.json](assets.json) | Fixed asset paths, immutable revisions, and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and task environment |
| [Environment configuration](environment/docker-compose.yaml) | Read-only mounts and hardware requests |
| [Verifier](tests/) | Execution, output validation, and scoring implementation |
| [Starter notes](environment/starter/README.md) | Teacher-side baseline and public validation |
| [Resource policy](environment/docs/available_resources.md) | Development access and offline submission rules |

### Data provenance and local checks

The packaged ArguAna corpus matches mteb/arguana commit
`6c1bcf74b13dfd823aff056b79d4d93e702f19c7`, with task-specific IDs; its source
license is CC BY-SA 4.0. The model family is described in
[Qwen3 Embedding](https://arxiv.org/abs/2506.05176v3), licensed Apache-2.0.
This frozen-index alignment task and its ridge reference are engineering
adaptations, not reported paper experiments. The original fixed matrix is
preserved byte-for-byte; its generation recipe is not reconstructed here.
The manifest pins 30 files totaling 8.72 GiB at immutable revisions, exact
sizes and hashes; public split and hidden split remain unchanged.

```bash
python -m unittest discover -s tasks/query-encoder-alignment/tests -p test_contract.py -v
python scripts/check_tasks.py tasks/query-encoder-alignment
```

Author calibration records and runtime evidence are kept under
`contributing/dev/query-encoder-alignment/v020/`, never mounted into a solving
agent. Public first-fit ridge Accuracy@1 is 54/100 with approximately 107 s
fit time on one A100 40GB. Two independent fits and public predictions are byte-identical. Hidden A0 is
62/100, frozen with implementation/data/prediction fingerprints in verifier-only
`tests/quality_baseline_lock.json`; fresh full verifier fitting reproduces it.
The repaired 4B reference scores 68/100. Known-baseline submission passes the
runtime, output and determinism checks and scores zero at its own quality anchor.
Historical artifact replay: Opus xhigh 76%, 36.8421/100 and time gate passed;
Luna xhigh 64%, quality 5.2632/100, time gate failed and retrieval reward zero.
These are retrieval replays, not new model solves or newly accepted judge runs.
The historical Codex 0.157.1 + OpenRouter `openai/gpt-6-luna`, effort `max` run
used the 12-hour development limit and scored **18.4211/100**: hidden Accuracy@1
69%, A0 62%, candidate 12.1705 s
against a 25.2756 s reference (15.1654 s limit). The repeat output is
byte-identical. The independent DeepSeek integrity judge accepted the submission;
`measurement_valid=true`, with no infrastructure exception. The solve took
36m48s and verification 6m51s, on a reserved A100 40GB. Agent/verifier memory
peaks were 10.80/10.88 GiB. Job:
`jobs/query-encoder-alignment-codex-openrouter-luna-max-v020-20261022-r2/2026-10-22__20-15-17/`.
The preceding r1 attempt was canceled before submission when an external
service occupied its reserved GPU; it has no valid model score. Both records
are retained. No scoring parameter changed between attempts.

This historical Luna/max solve supports the approximate 20-point difficulty
target; the historical Opus artifact replay scores below 50. A legal author
solution achieving 100% hidden accuracy has not been demonstrated; synthetic
grader tests establish the full-score numeric boundary only. Model-run evidence
for the six-hour budget will come from the release evaluations.

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

- [Task reference](https://arxiv.org/abs/2506.05176v3).
