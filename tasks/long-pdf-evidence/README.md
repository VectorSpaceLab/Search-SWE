# Long-PDF Sentence Evidence Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `long-pdf-evidence` |
| Version | 1.0.0 |
| Authors | Search-SWE, Bingyu |
| Primary metric | SentenceEvidenceAccuracy |
| Compute | 16 CPUs; 64 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 10800 s |
| Dataset | single long PDF |
| Hidden queries | 12 |

Retrieve up to five original sentence units that fully support a short interpretive question about *War and Peace*. The task uses **SentenceEvidenceAccuracy** with the DeepSeek evidence judge and a 30-second limit per query.

The unchanged PDF has 2,043 physical pages. Its question-independent inventory contains 28,798 units, preserving source-page provenance and normalizing PDF typography and whitespace. Unit boundaries are fixed for consistent evaluation, including dialogue and sentences crossing pages. The ten public and twelve hidden questions use disjoint reference units and opaque shuffled IDs. Questions ask about motives, tensions, reversals, or relationships without restating the relevant passage.

| Input | Role |
| --- | --- |
| `data/corpus/lp4P6AUxur.pdf` | Original shared novel |
| `data/corpus/sentences.jsonl` | Fixed sentence text, opaque IDs, physical source pages |
| `data/validation/queries.jsonl` | Ten public questions |
| `data/validation/golden_answers.jsonl` | Public support requirements and sufficient original evidence |
| `tests/data/` | Twelve private queries and references, excluded from agent mounts |

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

Interpretive questions about a long novel may refer to motives, relationships or reversals without repeating the relevant wording. The system must select at most five original sentence units that jointly provide complete support.

## Verification Explanation

### Contract, scoring and runtime

Deliver executable `/app/build.sh` and `/app/run.sh` following [instruction.md](instruction.md). Return `{query_id, results: [{sentence_id, sentence}]}`, with zero to five distinct units and no generated answer. Evidence order is irrelevant. The verifier checks corpus checksums, source membership, and output validity before judging sufficiency. Alternative correct evidence is accepted; reference IDs are not a scoring gate.

The answer judge is pinned to OpenRouter `deepseek/deepseek-v4.1-flash`, reasoning effort `high`, temperature 0. It awards 1 for complete evidence support and 0 otherwise. Mean support over all twelve questions is the metric; a failed or timed-out query remains in the denominator with zero. API/parse failures invalidate the measurement and fail closed, separately from ordinary unsupported evidence. A separate `deepseek/deepseek-v4.1-flash` trajectory audit through RewardKit 0.2.0 gates the final reward. Judge health and individual decisions are retained in verifier reports.

The CPU environment supplies 16 CPUs, 64 GiB memory, 100 GiB storage and no GPU. Development lasts at most two hours. Build receives 2,400 seconds; each query receives 30 seconds from invocation. The evaluator internally schedules up to five calls at a time, with a 1,800-second safety budget and 60 seconds for cleanup. These internal scheduling details are omitted from the agent-facing instruction. Answer judging is bounded at 2,700 seconds, with two workers, at most two attempts per request, and 10-second connect / 120-second read timeouts. Trajectory auditing is bounded at 3,600 seconds; the whole verifier allows 10,800 seconds.

Submission processes run as an unprivileged user. The verifier stages only the fixed corpus and query inputs for them, excludes judge credentials from their environment, terminates submission processes before judging, and protects private labels and reward files. `/app` is transferred into a fresh environment; service processes must be recreated by the build. See the [resource policy](environment/docs/available_resources.md) for the unchanged solver API allowlist. The semantic judge does not authorize solvers to call DeepSeek.

For local runs, configure an OpenRouter credential in `ANSWER_JUDGE_API_KEY`; the task pins `ANSWER_JUDGE_BASE_URL` and `ANSWER_JUDGE_MODEL_NAME`. Keep the trajectory judge's separate `VERIFIER_OPENAI_*` configuration. Optional solver APIs use `OPENROUTER_API_KEY` and `JINA_API_KEY`. Never store keys in the task package. The shared launcher accepts `--task long-pdf-evidence --model YOUR_AGENT_MODEL`; `--dry-run` only inspects command construction.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

Author development and calibration records live outside the package in `task_development/long-pdf-evidence` in the surrounding build workspace. [raw-instruction.md](raw-instruction.md) retains the structured specification and evaluator details; [instruction.md](instruction.md) presents the task, available inputs, executable interface, output requirements, limits and scoring criteria without data-construction explanations or judge implementation details. The prior task supplies the corpus, executable lifecycle and isolation pattern; `scientific-paper-qa` was consulted for separate semantic-judge credentials. The requested `agentic-search` reference currently uses deterministic GoldRecall@5, so its grader is not a semantic-judge implementation.

### Evidence-judge revision

The task pins DeepSeek V4.1 Flash in the grader, task metadata, verifier environment and structured authoring source. The agent-facing instruction describes the evidence requirements and 30-second per-query limit without naming the judge or explaining its implementation. The twelve questions, reference evidence, sufficiency rubric, averaging rule, reasoning effort and temperature are unchanged. The completed v0.4.3 Codex / `openai/gpt-6-luna` / `max` evaluation scored 1/12; both evidence evaluation and trajectory audit succeeded. See [RUN_RESULTS.md](RUN_RESULTS.md).

The earlier DeepSeek rejudgment of a Luna-generated submission returned 8/20 on the old twenty-question version. It is historical reference evidence, not a score for this twelve-question revision. The current trial's result and judge-health records are summarized in RUN_RESULTS.md.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task long-pdf-evidence
bash scripts/run_task.sh --task long-pdf-evidence --model YOUR_AGENT_MODEL
```

## References

None.
