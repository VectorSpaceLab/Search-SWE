# Task-1-3: Scientific-Paper Question Answering

Migrated from `harbor/tasks_v01/task-1-4` as version `0.3.0`. The submission
answers scientific questions using a local collection of PDFs and returns one
supporting document ID for each answer.

## Data and layout

| Path | Contents | Visibility |
| --- | --- | --- |
| `data/corpus/` | 300 scientific-paper PDFs | Agent and verifier, read-only |
| `data/validation/queries.jsonl` | 25 public development questions | Agent, read-only |
| `data/validation/golden_answers.jsonl` | Public answers and evidence document IDs | Agent, read-only |
| `tests/data/queries.jsonl` | 25 held-out questions | Verifier; staged after build |
| `tests/data/golden_answers.jsonl` | Private answers and evidence document IDs | Verifier only |

All PDFs, queries, and labels are byte-identical to the source task. Public and
hidden query IDs and questions are disjoint. Both splits search the same
300-PDF corpus. The original reference-only normalization of duplicate-file
suffixes in two source labels is preserved in the grader.

Public data lives at the task root, outside the Agent image build context.
`assets.json` records its file sizes and SHA-256 checksums. Both environments
mount the corpus and documentation read-only; only the Agent mounts public
validation. Harbor transfers `/app` and the Agent trajectory to the separate
verifier.

## Runtime and scoring

Both images use the local base
`search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0`. Resource limits remain
16 CPUs, 64 GiB RAM, 100 GiB storage, no GPU, a 7,200-second Agent phase, and a
14,400-second verifier phase. Submission commands run as the `submission`
user. `build.sh` has 3,600 seconds. The verifier then runs one `run.sh` process
per hidden query, with five workers and a 900-second deadline per launched
process. Queue time is excluded. Each query has separate input/output/log files;
results and timings are merged in input order. A query failure invalidates the
submission while the other queries still run. Commands must honor the supplied
index and output paths. `query_execution.json` records timings and errors.

The 14,400-second verifier phase covers build, query execution (a 4,800-second
shared guard), answer scoring (1,800 seconds), trajectory audit (3,600 seconds),
and finalization. Per-stage limits do not extend the phase budget.

Each result contains `query_id`, `answer`, and `evidence`. A query scores one
only if its evidence document matches the reference and the answer judge
accepts the answer as semantically equivalent. The base metric is the mean
`LLMJudgeAccuracy`; an independent trajectory audit gates the final reward.
Execution failures, invalid outputs, and a failed audit receive zero.

## Judge configuration

Use the separate placeholders in [`.env.example`](../../.env.example):

- `ANSWER_JUDGE_MODEL_NAME`, `ANSWER_JUDGE_BASE_URL`, `ANSWER_JUDGE_API_KEY`:
  semantic answer equivalence through an OpenAI-compatible Chat Completions API.
- `VERIFIER_OPENAI_BASE_URL`, `VERIFIER_OPENAI_API_KEY`:
  the Codex trajectory audit, using a Responses-compatible API. The URL/key
  names match the repository's `.env.example`; `task.toml` injects
  them as `OPENAI_BASE_URL` and `OPENAI_API_KEY` in the verifier. The audit
  model is fixed to `gpt-5.6-sol` in
  [`tests/jailbreak_judge/codex.toml`](tests/jailbreak_judge/codex.toml), matching
  Task-1-1. The answer judge uses its own model setting.

Set these variables in the repository `.env` or the environment that launches Harbor. They are
injected only into the verifier; submission processes receive neither group.
The answer scorer and trajectory judge are also launched without the other
group's settings. There is no cross-group credential fallback. Runtime configuration files contain model
names and API URLs but never API-key values.

Optional submission APIs use the shared `OPENROUTER_API_KEY` and `JINA_API_KEY`.
Harbor injects those names into both task environments. These are separate from
the private judge credentials and the launcher's coding-agent `AGENT_*` group.

The separate long-PDF evidence-localization task is [Task-1-4](../task-1-4/README.md).

## Validation

Data and evidence-gated scoring are preserved from the source task. Local tests
cover five workers over 25 questions, per-query deadlines, ordered results,
continued execution after one query fails, and exclusion of both judge keys
from submission environments. Container checks use local judge fixtures; live
external judge credentials are not required for these checks.
