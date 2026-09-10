# Task-1-4: Long-PDF Evidence Localization

Migrated from `harbor/tasks_v01/task-1-3` as version `0.3.0`. Given a query and
target PDF, the submission returns five distinct physical page numbers with
supporting text and ranked scores. The primary metric is macro `Recall@5`
over relevant pages, subject to the existing trajectory anti-jailbreak gate.

## Data and layout

| Path | Contents | Visibility |
| --- | --- | --- |
| `data/corpus/` | 6 public PDFs | Agent, read-only |
| `data/validation/queries.jsonl` | 30 public queries | Agent, read-only |
| `data/validation/ground_truth.jsonl` | Public page relevance labels | Agent, read-only |
| `data/validation/golden_answers.jsonl` | Original public label file | Agent, read-only |
| `data/verifier/corpus/` | 6 held-out PDFs | Verifier-only mount; staged read-only for submission execution |
| `tests/data/queries.jsonl` | 30 hidden queries | Verifier; staged after build |
| `tests/data/golden_answers.jsonl` | Hidden page relevance labels | Verifier only |

All PDFs, queries, and labels are byte-identical to the source task. Public and
hidden target PDFs are disjoint. Query IDs such as `q_001` are local to each
split and are reused across splits; the queries themselves differ.

Public data lives at the task root, outside the Agent image build context.
`assets.json` records its file sizes and SHA-256 checksums. The verifier mounts
`data/verifier/corpus/` read-only at `/tests/corpus`;
hidden queries and labels remain in its image. The Agent mounts only the public
`data/corpus/` and `data/validation/` directories.

## Runtime and verification

Both images use the local benchmark base
`search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0`. The task retains 16 CPUs,
64 GiB RAM, 100 GiB storage, no GPU, a 7,200-second Agent phase, and a
10,800-second verifier phase.

Harbor transfers `/app` and the Agent trajectory to the separate verifier.
Documentation is mounted read-only; public data is not mounted. The verifier
stages its hidden PDFs under `/tmp/task-1-4-eval/corpus`, then runs the submitted
`build.sh` and `run.sh` as the `submission` user. Both commands must honor their
supplied paths. The build may take 2,400 seconds; one run processes all 30
hidden queries within 1,800 seconds, using `--top-k 5`.

The deterministic grader validates query coverage, five unique in-range pages,
evidence membership on each reported page, finite descending scores, and
ascending page order for ties. It computes the mean fraction of relevant pages
retrieved. The existing Codex trajectory audit gates that score; invalid
execution, invalid output, or a failed audit receives zero. Audit credentials
remain private to the verifier; permitted submission APIs retain the source
task's configuration.

Task names, report paths, grader identifiers, and the audit prompt use
`task-1-4`. The source task remains available at its original path.

## Judge configuration

This task does not use an answer-correctness judge. Page relevance and Recall@5
are computed directly from the gold labels; the existing trajectory audit is
the only model-based gate.

Configure `VERIFIER_OPENAI_BASE_URL` and `VERIFIER_OPENAI_API_KEY` using
[`.env.example`](../../.env.example).
The URL/key names match the repository's `.env.example`; `task.toml`
maps them to `OPENAI_BASE_URL` and `OPENAI_API_KEY` inside the verifier. The
audit uses the Codex CLI and a Responses-compatible API. These variables are
excluded from submission commands and are independent of Task-1-3's
`ANSWER_JUDGE_*` settings. API-key values are never written into runtime
configuration files. The audit model is fixed to `gpt-5.6-sol` in
[`tests/jailbreak_judge/codex.toml`](tests/jailbreak_judge/codex.toml), matching
Task-1-1; no model-name environment variable is required.

Optional submission APIs use the shared `OPENROUTER_API_KEY` and `JINA_API_KEY`.
Harbor injects those names into both task environments. These are separate from
the private judge credentials and the launcher's coding-agent `AGENT_*` group.

## Validation

The data, deterministic page scorer, and executable interface are unchanged.
Migration checks covered both 30-question splits, page/evidence validation,
submission permissions, and process cleanup. Trajectory checks use a local
fixture; no live external judge is called during those checks.
