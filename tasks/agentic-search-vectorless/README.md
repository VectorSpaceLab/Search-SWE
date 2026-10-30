# Agentic Search — Vectorless

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `agentic-search-vectorless` |
| Version | 1.0.0 |
| Authors | Jianlyu |
| Primary metric | GoldRecall@5 |
| Compute | 32 CPUs; 16 GiB RAM; 200 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 19200 s |
| Dataset | BrowseComp-Plus |
| Hidden queries | 20 |

Build retrieval over the 100,195-document BrowseComp-Plus corpus without embeddings, BM25 or external retrieval/reranking. No starter, index or entry points are supplied, and neither the language nor retrieval architecture is prescribed. Each query may make at most 20 independent retrieval rounds. Twenty public questions and TREC labels support development; twenty hidden questions are scored with mean Gold Recall@5 after a mandatory compliance audit.

[raw-instruction.md](raw-instruction.md) is the structured specification. [instruction.md](instruction.md) is the complete prose request sent to the agent. The structured source is excluded from the agent's Docker context and mounts.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-25 | 1.0.0 | Added initial task |

## Difficulty Explanation

Retrieval must combine evidence across a large corpus within 20 retrieval rounds per query. The resource policy excludes embeddings, BM25 and external retrieval services, so the system needs an effective corpus navigation and evidence selection strategy.

## Verification Explanation

### Environment and verifier

The CPU shared image provides 32 CPUs, 16 GiB RAM and 200 GiB storage. Agent time is 7,200 seconds. The verifier discards the transferred `/app/index`, builds once as UID/GID 65534 and runs up to five query invocations sharing the fresh index and any optional build-started service. Build has a 600-second cap. Build, query execution and deterministic scoring share a 15,300-second wall-clock allowance, with no individual query timeout. The verifier has 19,200 seconds including a separate audit of up to 3,600 seconds. Any execution/output failure invalidates the entire submission.

Submitted processes receive an explicit environment allowlist and the task `OPENROUTER_API_KEY`, never judge credentials. The task-local `tests/trajectory_gate.py` orchestrates retrieval and the mandatory audit. After retrieval, submission processes stop before auditing. The judge uses RewardKit 0.2.0, LiteLLM 1.97.0 and Codex 0.164.0 with `deepseek/deepseek-v4.1-flash` at `https://openrouter.ai/api/v1`. Configure host `VERIFIER_OPENAI_BASE_URL` and `VERIFIER_OPENAI_API_KEY` locally; the latter is a separate OpenRouter judge key. Missing trajectory, bad output, judge failure/timeout or a detected violation leaves zero reward. Algorithm and round-limit auditing is not a formal guarantee of detecting every violation.

### Validation

From the repository root, restore inputs with `python scripts/download_assets.py --task agentic-search-vectorless`. Public upstream and published official HF inputs are permitted with immutable pins, exact filenames, sizes and hashes. Cross-task official asset reuse is supported from Search-SWE `ac7dcc1`; no duplicate publication is needed.

Use `python scripts/check_tasks.py tasks/agentic-search-vectorless`, `python scripts/download_assets.py --task agentic-search-vectorless --verify-only`, and `python -B -m unittest discover -s tasks/agentic-search-vectorless/tests -p 'test_*.py' -q`. Full trials use `bash scripts/run_task.sh --task agentic-search-vectorless --agent codex --openrouter --model openai/gpt-6-luna --reasoning-effort max` with locally configured agent, optional generation and verifier-judge credentials.

The historical October 15 Codex + OpenRouter `openai/gpt-6-luna`, effort `max`, trial used 128 GiB RAM and produced **Gold Recall@5 = 0**, compliance audit **1**, and final reward **0**. The verifier rebuilt the index in 460.82 seconds and completed all 20 query invocations in 154.15 seconds, with valid outputs and no scoring errors. The agent exhausted its 7,200-second development budget, so Harbor records `AgentTimeoutError`; the saved submission still received a valid zero score. This is evidence of working execution and auditing, not of positive retrieval quality. No setting was weakened or trial repeated merely because of the score.

The job is `jobs/evaluations/agentic-search-vectorless/codex/openai/gpt-6-luna/max/attempt-1/2026-10-15__14-05-14/`. Before the PR #17 fixes, all 28 recorded package file hashes matched the evaluated revision, apart from documentation changes. On October 17, against `ac7dcc1`, merge-ready checks, all 3 asset hashes, 22 task tests and the 174-test shared suite passed. These are historical results; v0.2.2 subsequently clarifies the audit's permitted query-input interface. Public and hidden query IDs and gold document IDs are disjoint. The author review is `contributing/dev/contribution-readiness/2026-10-17/REVIEW.md`.

#### PR #17 audit clarification (v0.2.2)

The audit explicitly permits reading the query file passed to `run.sh --queries`
during formal query execution. Obtaining hidden queries outside that interface,
reading hidden labels/evaluation answers, hard-coded hidden mappings, and
verifier-state manipulation remain prohibited. Task instructions, retrieval
constraints, budgets, and the scoring formula are unchanged.

On October 17, the revised package passed all **23 task-local tests**, merge-ready
checks against `ac7dcc145925d98afd2b0db1112d7c0ad8ba1460`, all **3 asset** hash
checks, release checks, and the **174-test shared suite**. The new rubric
regression covers both the legitimate input exception and the retained bans.
These checks are separate from the historical zero-score coding-model trial.

#### Real-corpus known-good verification (October 17, 128 GiB RAM)

An author-only reference submission was frozen after public-only calibration
(public Gold Recall@5 **0.115833**, 6/20 questions with hits). It reuses the earlier
model's corpus index builder and ranks one lexical candidate pool per query by
binary term coverage within passages. It uses no embeddings, BM25, external
services, hidden labels, or hard-coded query-to-document mappings. The reference
was not modified after observing hidden results.

Native Harbor Oracle installed the frozen source in an author-only task copy;
normal artifact transfer then exercised the **same v0.2.2 build/run/scorer/audit
pipeline**, separate verifier, network policy and resource limits. No prebuilt
index was transferred. The verifier rebuilt all **100,195 documents in 462.74
seconds**, ran **20/20 queries with concurrency 5 in 232.20 seconds**, and scored
them in **12.08 seconds**. All commands succeeded and outputs were valid.

Observed hidden **Gold Recall@5 = 0.05**, **jailbreak_judge = 1**, and **final
reward = 0.05**. The real OpenRouter `deepseek/deepseek-v4.1-flash` audit returned
status 0, and the complete verifier finished in **1,026.74 seconds** without a
trial exception. No task constraint, scoring rule or time budget was relaxed.

This is a known-good replay, not a new blind Luna coding-model trial. Its audit
record retains all 41 original model trajectory steps unchanged and explicitly
adds the actual maintainer reference-development tool records and Oracle
installation receipt as separate system records. No new model actions are
invented. The historical zero-score Luna trial remains separate evidence.

Evidence: `jobs/agentic-search-vectorless-known-good-20261017-pr17/2026-10-17__13-57-45/task__cYHQDPj/`.
The reference source, pre-hidden freeze hashes, exact native Harbor command,
provenance checks and results are retained under
`contributing/dev/agentic-search-vectorless/2026-10-17-pr17/`, outside the public
task package. The query implementation SHA-256 is
`a6beacc387cc65d219cee356563164e95e32275ccc48b48589c073d8511dea1d`.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task agentic-search-vectorless
bash scripts/run_task.sh --task agentic-search-vectorless --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max
```

## References

### Sources and structural references

The corpus/public split has the exact current `tasks/agentic-search/assets.json` hashes and named paths, pinned to official dataset revision `6713b1eb7474e0768e906a0151c76af92f0cfcdd`. No source bytes were changed or republished. See [SOURCES.md](SOURCES.md) for provenance and usage terms. Published inputs may be reused at their original paths. The hidden split remains runtime-isolated but visible to repository readers; it is not a secret evaluation set.

Read-only references: `tasks/agentic-search` for corpus layout, build/query lifecycle and deterministic Recall scoring, and `tasks/long-pdf-evidence` for the current trajectory-judge backend. Intentional differences: no ReAct/BM25 starter, no embeddings or BM25, no external retrieval/reranking, and a broader audit of the embedding/BM25 bans and other task constraints; the reviewed task now also has a trajectory audit. The allowed Qwen generation models remain those in this package's resource document.
