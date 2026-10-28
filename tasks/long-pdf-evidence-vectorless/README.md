# Long-PDF Sentence Evidence — Vectorless

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `long-pdf-evidence-vectorless` |
| Version | 1.0.0 |
| Authors | Jianlyu |
| Primary metric | SentenceEvidenceAccuracy |
| Compute | 16 CPUs; 16 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 10800 s |
| Dataset | single long PDF |
| Hidden queries | 12 |

Build a reusable, embedding-free index over the supplied *War and Peace* PDF and its fixed sentence inventory. Return up to five complete original sentence units supporting each interpretive question. The task uses **SentenceEvidenceAccuracy** and the sentence-evidence inputs attributed in [SOURCES.md](SOURCES.md).

The unchanged PDF has 2,043 physical pages; the question-independent inventory has 28,798 units. Ten public questions include support requirements and sufficient evidence. Twelve private questions use disjoint reference units. Page numbers are provenance only; alternative correct sentence evidence is accepted. See [instruction.md](instruction.md) for the agent request and [raw-instruction.md](raw-instruction.md) for the structured contract.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Added initial task |

## Difficulty Explanation

The system must construct a reusable embedding-free index and retrieve original sentence evidence from a long novel. Evidence must jointly support the question within the output and runtime budgets.

## Verification Explanation

### Runtime and isolation

The CPU image provides 16 CPUs, 16 GiB RAM and 100 GiB storage, without a GPU. Development is limited to 7,200 seconds. `/app/build.sh` creates a persistent index in 2,400 seconds. All build workers stop before private queries become visible, and the staged PDF **and sentence inventory** become root-owned (files 0400, directories 0700). Query processing must use only the index, supplied queries and submission code. Optional query-time services must start from that index alone. Embeddings are prohibited during both build and search; lexical indexing and permitted generation/non-embedding reranking remain available.

The fresh separate verifier transfers `/app`, rebuilds the index, and runs submission commands as UID 10001. Up to five query processes share the index, each with 900 seconds and a shared 1,800-second deadline; cleanup has another 60 seconds. Failed or invalid queries remain in the twelve-query denominator with zero. The root-side grader reads a private corpus mount to verify fixed hashes and original sentence membership. Public validation and all judge credentials are excluded from submission processes.

The answer judge uses OpenRouter `deepseek/deepseek-v4.1-flash`, effort `high`, temperature 0, two workers and at most two attempts/request, within 2,700 seconds. Complete evidence support earns 1; topical or incomplete evidence earns 0. API/parse failure invalidates the measurement and fails closed. The separate trajectory audit uses RewardKit 0.2.0, LiteLLM 1.97.0 and Codex 0.164.0 with `deepseek/deepseek-v4.1-flash`, bounded at 3,600 seconds. Only a valid binary audit pass preserves accuracy as the final 0–1 reward. The entire verifier has 10,800 seconds.

### Evidence judge calibration

The judge evaluates requirements by their semantic support in the question and
candidate evidence. Equivalent explanations may establish a distinction without
repeating the reference's wording or separately negating alternatives. Requested
comparisons, qualifications and causal links remain necessary. Extra evidence affects
support when it creates a material contradiction or an unresolved essential referent;
harmless redundancy is allowed. Rejection reasons identify the missing necessary
relationship or concrete conflict.

`tests/judge_calibration.json` contains ten synthetic positive/negative cases covering
causality, contrast, qualifications, reference resolution, contradiction and temporal
context. These author-only cases are not part of scored data or the production prompt.
`tests/test_judge_request.py` mocks HTTP to check request contents and failure handling;
it does not establish the model's semantic decisions. See [VALIDATION.md](VALIDATION.md)
for local checks and the pending live calibration/re-evaluation handoff.

### Credentials and evaluation

Configure the ignored repository `.env`: `AGENT_OPENROUTER_API_KEY` for the coding agent; `ANSWER_JUDGE_API_KEY` for the semantic judge; and `VERIFIER_OPENAI_API_KEY` / `VERIFIER_OPENAI_BASE_URL` for the trajectory audit. Both judge endpoints are `https://openrouter.ai/api/v1`. Set `ANSWER_JUDGE_BASE_URL` to that endpoint and `ANSWER_JUDGE_MODEL_NAME` to `deepseek/deepseek-v4.1-flash` for launcher validation; the task also pins both values. Optional solver calls use the separate `OPENROUTER_API_KEY` and only the models/endpoints in [available_resources.md](environment/docs/available_resources.md). The judge model is not a solver resource. Never include credential values in this package or artifacts.

From the repository root, using the configured Python environment:

```bash
python scripts/download_assets.py --task long-pdf-evidence-vectorless
python scripts/download_assets.py --task long-pdf-evidence-vectorless --verify-only
python scripts/check_tasks.py tasks/long-pdf-evidence-vectorless
python -B -m unittest discover -s tasks/long-pdf-evidence-vectorless/tests -p 'test_*.py' -v
bash scripts/run_task.sh --task long-pdf-evidence-vectorless --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output jobs/long-pdf-evidence-vectorless-codex-openrouter-luna-max-RUN_ID
```

### Sources and validation status

All four public inputs use the reviewed original task's published immutable pins, sizes and SHA-256 hashes. Private queries/references are reused unchanged from its v0.4.1 verifier. See [SOURCES.md](SOURCES.md) for provenance and publication limits. Private files are excluded from agent mounts but remain visible to repository readers, so this is not a secret evaluation set.

Reviewed precedent: `tasks/long-pdf-evidence` at `f1c4f57`, selected for the same data, sentence-evidence scorer, semantic judge, CPU environment and submission interfaces. This variant preserves its own no-embedding policy, index-only boundary, build-worker termination, private grader corpus and strict binary audit gate. It does not inherit the original task's embedding APIs or persistent build service.

Authoring and validation evidence is recorded outside the package in `contributing/dev/long-pdf-evidence-vectorless/2026-10-16/`. All four assets, 20 task tests, 173 shared tests, both image builds and a disposable-container boundary check passed. At the contributor's request, this revision uses DeepSeek v4.1 Flash through OpenRouter for answer judging. A public positive/negative probe passed using the existing authorized verifier credential. The default local `.env` now also assigns that credential to answer judging; the separate solver credential is unchanged.

The historical October 16 Codex + OpenRouter Luna max trial used 64 GiB RAM and completed verification with **SentenceEvidenceAccuracy = 0.25 (3/12)**, compliance audit **1**, and final reward **0.25**. All twelve hidden queries executed successfully in 438.15 seconds; output-invalid and answer-judge-error counts were both zero. The coding agent exhausted its 7,200-second development budget, so Harbor records `AgentTimeoutError` even though its saved submission received a valid score. This was one formal attempt with no retry, not an uninterrupted agent completion. Results are in `jobs/long-pdf-evidence-vectorless-codex-openrouter-luna-max-20261016-attempt1/2026-10-16__20-03-01/`; the author report is `contributing/dev/long-pdf-evidence-vectorless/2026-10-16/RESULTS.md`.

The four public inputs intentionally reuse the original task's published paths and immutable pins. Search-SWE `ac7dcc1` supports cross-task reuse while retaining source-path and integrity checks. On October 17, both checkouts and remote main contained that fix; this package passed the contribution checkout's merge-ready checker without asset changes. All 4 asset hashes, 20 task tests and the 174-test shared suite passed. The proposed duplicate upload was cancelled, and no data was published. See `contributing/dev/contribution-readiness/2026-10-17/REVIEW.md` for the current review.

A public cart-purpose question omits the requester, allowing competing original scenes. Its supplied public reference requirements identify the intended furniture request; this observation does not invalidate the separate hidden-set measurement. On October 17 the contributor requested retaining wording unless modification was necessary, so the original public data are retained and this optional clarification is not a submission blocker. The diagnostic and proposed wording remain recorded in `public-query-ambiguity.md` under the October 16 author evidence directory. No question, grader or resource budget was changed in this review.

## References

- [Data, model and method provenance](SOURCES.md).
