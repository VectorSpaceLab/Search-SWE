# Local validation

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

## Baseline revision — 2026-10-23, v0.1.1

The user selected **0.1838** as the new zero-reward baseline. It is the rounded
nDCG@10 of the archived BM25 + Qwen3-Embedding-8B hybrid run (top-1000 each,
RRF 60): **0.1838410794397215**. Source:
`../../../task_development/quantity-aware-retrieval/research/medquant-baselines-v1/summary.json`,
`methods.hybrid`. The reward is now `max(0, min(1, (Q-0.1838)/(1-0.1838)))`.

The saved Codex / `openai/gpt-6-luna` / `max` trial from 2026-10-22 has valid
results for 210 queries, raw nDCG@10 **0.3157221500219995**, and a successful,
passing trajectory judge. Applying the new formula gives final reward
**0.161629686378338**; its original reward under baseline 0.3174 was zero.
This is an offline recalculation using the saved evaluation and integrity gate,
not a new agent or judge run. The original run artifacts are preserved at
`../../../task_results/quantity-aware-retrieval/codex-openrouter-gpt-6-luna-max-v010-20261022T135859Z/jobs/2026-10-22__21-59-35/quantity-aware-retrieval__63D7YGN/verifier/`.
The evidence files are `quantity-aware-retrieval-eval/evaluation.json`,
`reward.json`, and `reward-details.json` (`final_gate`).

Validation for this revision: all eight task-local unit tests passed; the TOML
and grader baseline agree; the production scoring/finalizer functions reproduce
the recalculated reward using the saved integrity gate. `instruction.md` is
unchanged. The task static checker still reports the two existing unpublished
data revision errors for `data/corpus.jsonl` and `data/examples.jsonl`.

## Archived packaging validation — 2026-10-14, v0.1.0

Everything below records the original packaging checks, with baseline 0.3174.
Statements about unperformed trials and scores describe that historical revision.

This is a locally constructed package with tested data, model compatibility,
retrieval interface and deterministic grading. It has **not** completed a live
coding-model/trajectory-judge trial and is **not ready for remote release**.
No model API calls, remote uploads, commits or pushes were made during packaging.

Author-side scripts, fixtures, logs and machine-readable evidence live at
`../../../task_development/quantity-aware-retrieval/validation/`. They are not
mounted into the agent environment. `evidence.json` records the final task-file
hashes, data hashes, model checks and individual container outcomes.

## Final setting

- 153,252 unchanged MedQuant passages, 80,000 labeled examples at
  `data/examples.jsonl`, and all 210 original questions/qrels private. Public
  retrieval validation was removed at the user's request.
- The measured frozen reference is 0.31736759004837656. The user selected its
  rounded value, **0.3174**, as the exact zero anchor. Quality Q maps to
  `max(0, min(1, (Q-0.3174)/(1-0.3174)))`.
- One A100 40GB, 16 CPU cores, 32 GiB RAM; 21,600 seconds (6 hours) for development,
  1,200 seconds for verifier index/service startup and 5 seconds per query call.
- Qwen3-Embedding-0.6B and documented APIs are available. The instructions
  specify the required behavior without implementation suggestions; agent and
  verifier use separate GPU containers.

The current revision sets development to six hours, removes
`tests/data/config.json`, and keeps the fixed evaluation constants in
`tests/grader.py`. The output-size cap is removed from both instructions and
the verifier. Data explanations, source-label caveats and baseline calibration
are omitted from the instructions at the user's request; the public objective
remains hidden-test mean nDCG@10. Corpus, examples, private questions/qrels and
the score formula are unchanged. Earlier validation summaries and contract
files are retained under `validation/revisions/before-six-hour-simplification/`.
All eight task unit tests and all twelve container cases were rerun successfully
against the current contract. `validation/six-hour-revision.json` records the
revision and `validation/six-hour-static.json` records the static checks. No new
coding-model or live judge trial is implied by these changes.

## Completed checks

| Check | Observed result |
| --- | --- |
| Task-local unit tests | 8 passed: nDCG denominator, normalization, IDs/scores/order, regular output files and judge/credential boundaries; valid JSONL larger than 64 KiB is accepted |
| Targeted repository tests | 21 ran successfully; 2 RewardKit-dependent host tests skipped because RewardKit is installed in the verifier image, not the host |
| Fixed assets | All 12 files passed size and SHA-256 verification; two data files and ten model files |
| Data isolation | No validation files remain in public task data or local asset staging; no evaluation labels or parsed quantity annotations enter public corpus/training records |
| Local staging check | Zero errors with the official `check_release(..., allow_unpublished=True, hf_data=...)`; expected unpublished-data warning |
| Strict static check | Exactly two errors: unpublished corpus and training asset revisions are null; no fabricated release pins |
| GPU environment template | `environment/docs/environment.md` is byte-identical to `docker/gpu/environment.md` |
| Docker builds and Compose | Both images built; both GPU Compose overlays validate with the official temporary-base procedure |
| Harbor schema | Harbor 0.22.0 `TaskConfig` parsed the final task with one GPU and separate verification |
| Shell/diff checks | `bash -n tests/test.sh` and `git diff --check` passed |
| Launcher preview | `--agent codex --openrouter --dry-run` succeeded using existing local configuration; no job launched |

The direct Codex launcher preview without `--openrouter` initially reported
missing `AGENT_OPENAI_BASE_URL`. The existing OpenRouter configuration was used
for the successful preview. No shared `.env` values were changed or printed.
A preview does not authenticate any model endpoint or exercise Harbor execution.

A broader `python -m unittest discover -s scripts/tests -p 'test_*.py' -q`
attempt did **not** finish. The host Python 3.13 runner reported that its async
executor failed to join threads within 300 seconds; the author stopped only that
test worker with SIGINT and preserved the traceback in `repository-tests.log`.
The stack was in `IsolatedAsyncioTestCase` runner teardown. This is an incomplete
whole-repository check, not a passing suite; no unrelated test/harness files were
changed to suppress it. The task-local tests, relevant targeted repository tests,
and all 12 task container cases completed separately.

Both local images use the repository GPU base. Built image IDs:

- Agent: `sha256:8e678e08275755da5179ba882b34346fdfaf4a40c8b8b03804641f91e98bd9a0`.
- Verifier: `sha256:c4d1aeb875621c747449e8c758c2d4f0c86c18248a51b81198099f330d22e34a`.

## Container execution evidence

`validate_task_runtime.py` ran 12 cases in disposable containers with networking
disabled, one visible A100 and the published CPU/RAM limits. Artifacts were
copied into `/app`; corpus/model/docs were read-only mounts. The same production
permission setup and grader were used. Each valid case processed all 210 queries
with newly assigned request IDs. No fixture is a public solution.

| Case | Observed result |
| --- | --- |
| Perfect-answer arithmetic fixture | Raw nDCG 1; normalized quality 1 |
| Replay of frozen reference rankings | Raw nDCG 0.31736759004837656; normalized quality 0 |
| Empty rankings | Valid output; raw nDCG and normalized quality 0 |
| Missing output, malformed JSON, duplicate IDs, nonzero query exit, failed build | All five cases rejected; task quality 0 |
| One query sleeping 5.5 seconds | Exactly one timeout; remaining 209 queries still evaluated; raw nDCG 209/210 |
| Permission/credential probes | UID 10001; hidden tests/labels/trajectory unreadable; reward, trajectory and `/app` unwritable; judge sentinels excluded from child environment |
| Production `test.sh` with missing judge credentials | Perfect raw metric still produced **final reward 0** and exit 1 |
| Genuine BM25 retrieval | Raw nDCG 0.14923940061811164, matching the prior independent run; normalized quality 0; no timeouts |

The BM25 implementation built its complete corpus index in **7.98 seconds** and
kept a resident retrieval service. Whole-call p95 was **0.116 seconds**, rounded
up. It receives no answer table, qrels or parsed source annotations. The other
answer-replay fixtures deliberately test scoring only and are not evidence of
legitimate optimal retrieval. Submission processes were stopped before each
container was removed.

The production integrity judge was not replaced or bypassed in the formal task.
Most author checks call the grader directly after the production permission
setup; the missing-judge case invokes the full production `test.sh` and verifies
failure behavior. These checks do not count as a live integrity-judged trial.

In **both** images from the preceding revision, a non-root process loaded the supplied 0.6B weights,
encoded six texts from two supplied triples, backpropagated a finite pairwise
loss and performed one AdamW update. Each container saw one A100 40GB. Peak
allocated GPU memory was **5.57 GiB** at maximum sequence length 128. This proves
basic model/training compatibility only; it does not estimate full 80k training
time or demonstrate retrieval improvement. No updated weights were saved. This
model smoke test was not repeated for the current verifier-only changes; model
files, dependencies and image layers below the verifier source are unchanged.

## Source-to-request review

Reviewed precedents were `tasks/reasoning-query-rewriting` for retrieval/API and
separate-verifier structure, and `tasks/query-encoder-alignment` for GPU/model
resources. `tasks/negative-constraint-retrieval` was an additional local example
for per-query limits and protected execution. No task-specific labels, thresholds
or license claims were copied from those tasks.

| Structured source condition | Agent-facing text and implementation |
| --- | --- |
| Clinical numerical retrieval | Opening instruction |
| Corpus/examples and file availability | File paths and submission paragraph, resource file table, phase-specific Compose mounts; supplied data fields are left for inspection |
| Model/API/integrity restrictions | Resource paragraphs and linked resource policy; exact trajectory-judge rubric and child environment filtering |
| Persistent `/app` artifacts; read-only verifier execution | Submission paragraph; ownership/permissions in `test.sh`, UID drop in `grader.py` |
| Build/run flags, JSONL result, 0–10 distinct IDs and finite ordered scores | Fenced commands and output paragraph; `grader.py` and `scoring.py` |
| Six-hour development, 1,200-second build and 5-second query limits | Resource/build/timing paragraphs; task.toml and per-call timed subprocesses, timeout-zero behavior |
| Hidden-test nDCG objective and task/individual failure rules | Final instruction paragraphs; scoring/finalization modules and negative cases |

Fenced command examples intentionally follow the user's explicit preference,
despite the instruction-rewrite reference's generic preference for unfenced
prose. Hardware and execution budgets appear in the instruction; package listings
stay in the environment document. Baseline
implementations and authoring helpers remain outside the formal package, as the
user requested. The complete original positive sets, IDCG calculation and fixed
0.3174 anchor remain internal grading details. Source-label conventions are
retained in author-facing provenance. This intentionally follows the user's
request for a shorter task statement. No scoring or difficulty changes were
made from the fixture results.

## Remaining validation and release steps

The configured coding-model trial is **not run**: there is no evaluated coding
model/effort, genuine agent trajectory, live judge health result, or trial reward.
The repository skill requires that validation layer, but also states that local
authoring “does not itself authorize” spending on model APIs/GPU jobs. The user
authorized the local GPU checks; no new paid coding-model/judge run was launched.
See [create-searchswe-task](../../.agents/skills/create-searchswe-task/SKILL.md).

An authorized trial can use the ignored repository `.env` OpenRouter configuration
with `AGENT_MODEL`, `AGENT_OPENROUTER_API_KEY`, `VERIFIER_OPENAI_BASE_URL` and
`VERIFIER_OPENAI_API_KEY`, and a fresh output directory. Direct Codex instead
needs `AGENT_OPENAI_BASE_URL` and `AGENT_OPENAI_API_KEY`. Optional submission APIs
use `OPENROUTER_API_KEY` and `JINA_API_KEY`. Do not put any credential in this task.
Only credential presence and launcher configuration were checked; endpoint health
and API latency remain unmeasured. Existing local 8B baseline latency evidence
does not establish API service latency.

The two derived dataset assets are staged locally but have no published HF
revision. Redistribution terms still need source-specific review before remote
publication, followed by real immutable pins and strict release validation.
Original positive-only qrels may omit relevant passages, and training labels are
synthetic/noisy. Neither full label auditing nor training-benefit/50k-versus-80k
ablations were performed. These are explicit measurement limits.

Reproduction commands, from the Search-SWE root:

```bash
python scripts/download_assets.py --task quantity-aware-retrieval --verify-only
python -m unittest discover -s tasks/quantity-aware-retrieval/tests -p 'test_*.py'
python scripts/run_task.py --task quantity-aware-retrieval --agent codex --openrouter --dry-run
python ../task_development/quantity-aware-retrieval/scripts/validate_task_runtime.py --gpu 2
```
