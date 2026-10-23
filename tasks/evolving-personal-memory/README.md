# Personal-History Search and Answering

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `evolving-personal-memory` |
| Version | 1.0.0 |
| Authors | Haoran Jin |
| Primary metric | FAMA |
| Compute | 8 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 21600 s |
| Dataset | Memora |
| Hidden queries | 595 |

Retrieve original conversation records and answer questions about a person's history at a specified cutoff.

### Overview

Personal facts can change across conversations. A reusable search system
must identify records relevant to a question and its session cutoff, then
answer using only the selected records.

Retrieval and answering are separate stages. The verifier loads complete
original records for the IDs returned by search; the answer process has no
access to the full history or index.

### Task Setup

#### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus/records.jsonl` | 27,614 original sessions for 30 personas |
| `data/validation/queries.jsonl` | Five public development questions |
| `data/validation/labels.jsonl` | Public memory and forgetting criteria |

Public data are mounted read-only under `/task/data`, local models where
provided under `/task/models`, and resource documents under `/task/docs`.
Held-out questions and labels are verifier-only.

Inputs come from [Memora](https://github.com/geniesinc/Memora) at revision
`a6493188efc836d6511ed5e4163fe3ba87da30ff`, released under Apache-2.0.
The histories are synthetic. All 600 original questions are retained: five
public examples and 595 held-out questions. The complete history is shared.

Source criteria were deduplicated within each question by criterion text,
expected decision and type. No new questions or criteria were generated.
All original task types and time horizons remain in the combined data.

#### Fixed Components and Allowed Changes

Conversation records, question cutoffs and the search/answer interfaces are
fixed. Indexing, retrieval and answer organization are implementation choices;
no starter is supplied. Search may return up to 350 unique original records
for the requested person, with session IDs no later than the cutoff.

Only records selected by search become answer-stage inputs. Optional APIs and
stage-specific access follow the [resource policy](environment/docs/available_resources.md).

#### Environment and Resource Limits

The CPU environment provides eight CPU cores, 32 GiB RAM, 100 GiB storage and
no GPU. Development has two hours; the verifier has six hours.
Build has 1,800 seconds, and each of two search calls has 1,800 seconds.
Answer processes have 600 seconds each after launch, with up to eight running
concurrently and a shared 7,200-second answer-stage budget.

Records are passed in full. A 350-record request can be approximately 1.08 MB,
and may require more than one permitted model call.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

- Retrieving useful records from long personal histories.
- Respecting the requested person and session cutoff.
- Organizing an answer from a bounded set of complete records.
- Separating retrieval resources from per-request answer execution.

## Verification Explanation

### Submission Contract

Submit executable `/app/build.sh`, `/app/search.sh` and `/app/answer.sh`
with their supporting files. Answer-side code and configuration live under
`/app/answer/`. Search returns record IDs; answer receives a JSON request
containing their complete text and returns the query ID and a natural-language
answer. [instruction.md](instruction.md) includes complete interface examples.

Build and search run unprivileged with read-only code and corpus. The supplied
index directory is writable across search calls; its parent is not writable.
Answer processes use separate non-root roles and per-request filesystem
allowlists. They can read only current inputs, answer code, required system
libraries and their own writable workspace. The corpus, index, other requests,
hidden criteria and judge credentials are inaccessible.

The full schema and invocation details are in [instruction.md](instruction.md).

### Evaluation

#### Search Quality

Three independent judge configurations vote on each deduplicated criterion.
MPA measures passed memory criteria, FAA measures passed forgetting criteria,
and lambda is the fraction of criteria that concern forgetting.

```text
FAMA = max(0, MPA - lambda * (1 - FAA))
```

Final quality is mean FAMA over 595 held-out questions. Retrieval IDs assemble the answer request and are not a
separate retrieval-quality metric. Record IDs are not appended to judged answer
text.

#### Score Normalization

The final reward uses the raw quality described above, with fixed reference
quality `b = 0.3712215103709065` and integer score anchor `a = 20` on the 0–100 scale:

```text
reward(q) = (a / 100) * q / b                             if 0 <= q <= b
            a / 100 + (1 - a / 100) * (q - b) / (1 - b)  if b < q <= 1
```

This maps raw quality 0, b and 1 to rewards 0, a / 100 and 1. Raw quality and
auxiliary diagnostics are reported separately. Harbor retains the 0–1 reward
precision; a displayed 0–100 score is rounded to one decimal place.
Correctness and trajectory-audit gates take precedence over this conversion.

#### Correctness and Resource Gates

Executable behavior, eligible record IDs, answer format, query coverage and
stage limits are checked. Build and search stop before answer execution.
Each answer process tree and workspace are removed before its role is reused.
Transport or malformed-response failures in trusted judging invalidate the
measurement and must not be interpreted as model quality.

#### Integrity Checks and Final Reward

A separate trajectory audit checks task compliance and gates the quality
reward. A confirmed violation sets reward to zero; unavailable or incomplete
audit results are not valid evidence of model quality. The audit uses pinned
RewardKit 0.2.0 with verifier-only OpenRouter settings.

Private questions, reference labels and audit credentials are excluded from
the agent environment and protected from submitted programs. Answer judges,
where used, are distinct from trajectory auditing.

### Running This Task

Follow the repository [quick start](../../docs/quickstart.md) to prepare Harbor
and Docker, the [evaluation guide](../../docs/evaluation.md) for agent and
credential configuration, and the [asset guide](../../docs/assets.md) for
restoring fixed inputs.

Optional task APIs use `OPENROUTER_API_KEY` and `JINA_API_KEY` where the
resource policy permits them. Trajectory auditing uses the separate verifier
credential group `VERIFIER_OPENAI_*`.

Semantic judging additionally uses verifier-only `MEMORA_JUDGE_*` settings
from `task.toml`. These credentials and the trajectory-audit credentials are
not submission resources.

The commands below apply in a checkout with this package installed at
`tasks/evolving-personal-memory/`:

```bash
python scripts/download_assets.py --task evolving-personal-memory
bash scripts/run_task.sh --task evolving-personal-memory --model "YOUR_AGENT_MODEL"
```

The shared launcher defaults to Codex and also supports Pi and Claude Code.
Replace `YOUR_AGENT_MODEL` with the configured model. Add `--dry-run` to inspect
launch construction without starting an evaluation; it does not validate assets,
credentials or hardware. Results are written under `jobs/evolving-personal-memory/`.

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
