# Local validation

## Query removal — 2026-10-28, v1.0.0

Removed these three hidden queries for 魯隱公二年四月 and their qrels rows:

- `query_0a0f0c586a62ce91a86f4ee6`
- `query_f1aa6ed34a522f97c291e5e3`
- `query_2c213f84637f1595e3f2e81f`

All three used `doc_086389fc7d08e192db320dcb` and
`doc_6ee1a8ee1c6f5c792a1b060e` as positives. The first says
"夏，莒人入向，以姜氏還" without specifying April; the corpus also contains
"夏，五月，莒人入向" for the same event. The second passage describes 無駭入極
without specifying a month. The user selected removal of the three precise-month
queries. The passages remain in the corpus and in the qrels of retained queries.

The hidden set now contains **775 queries**, with the retained rows unchanged.
Corpus, public examples, dated examples, runtime limits and the nDCG@10 formula
are unchanged. The grader averages over the 775 retained queries; this task has
no baseline subtraction or normalization anchor to recalculate. The package
version remains **1.0.0**. Historical model scores below use the earlier
778-query set and have not been recalculated; no new model or judge run was made.

Validation: all ten task-local tests passed, including production data loading
and query-count agreement with `task.toml`. The task static checker reported zero
errors. Comparison with the previous revision confirmed that each private JSONL
file lost exactly the three specified rows and retained every other row unchanged.
The corpus and both public example files still match their published SHA-256
checksums. `git diff --check` passed.

## Archived local validation — 2026-10-14

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

This local package has been built and exercised through its real submission
interface. A configured coding-agent trial and paid trajectory-judge run have
not been performed; the task is not claimed release-ready.

## Frozen configuration

- Reviewed repository base: `46197a43f8cbb364e72b6d63d5db873ae7d2cac8`.
- Source commit: `392d6ec8d62de8256b3b45578f7b4484c22042ce`.
- Corpus: 18,662; public examples: 6,617; hidden questions: 778; no validation set.
- Development: 21,600 s; build: 1,200 s; complete query batch: 120 s.
- One NVIDIA A100-SXM4-40GB, 16 CPU limit, 32 GiB container memory.
- Raw instruction SHA-256: `39ef66478ea2d6b97861d53bfba7caf4a9d02a13d5d385f994e3f3da9670446b`.
- Rewritten instruction SHA-256: `7b6333047d5598805c7ff3c09dafc57eabc94f94948362f48b6aca2127f816dc`.

The structured source and request were reviewed for goal, files, policy,
transfer, read-only paths, build lifecycle, CLI, output, ranking, deadlines,
failure scope and metric. Command fences are retained at the user's explicit
request. The environment document matches `docker/gpu/environment.md` exactly.

## Executed checks

- `python scripts/download_assets.py --task chunqiu-temporal-retrieval --verify-only`:
  all 13 files verified, zero failures (1.13 GiB).
- `python -m unittest discover -s tasks/chunqiu-temporal-retrieval/tests -p 'test_*.py' -v`:
  10 tests passed, including the nDCG ideal denominator, complete-batch coverage,
  scores/order/duplicates, nonregular output files, deadline and credential gates.
- Repository image/network/RewardKit integration suites: 21 tests, zero failures,
  two optional host-dependency tests skipped. The modified RewardKit inventory
  and credential-boundary suite was checked again after its final entry change.
- Both Compose overlays rendered with a temporary base service; Harbor 0.22
  schema validation accepted task.toml; `git diff --check` passed.
- `check_release(..., packages=[task], verify_data=True, allow_unpublished=True)`
  with the local staged manifest: no errors, one unpublished-data warning.
- Strict `check_tasks.py`: exactly three expected errors for unpublished dataset
  revision pins. This is recorded as an outstanding publication prerequisite,
  not a passing release check.
- Source audit confirms byte-preserved corpus text, unchanged retained query
  text, exact retained event qrels, original month splits, no conflicting labels
  for identical positive text, and training-only public date associations.

Both task images were built from their own Dockerfiles:

- Agent: `search-swe-local:bingyu-chunqiu-agent-v010`,
  `sha256:79b4a38eeb3062cba01acd778fba494f370d7ae4b5b8f7e425591814801dab0e`.
- Verifier: `search-swe-local:bingyu-chunqiu-verifier-v010`,
  `sha256:1e4e4335c18e0a30b12e022a213175a2b6494b6fe8ff0a5e2c4ec92d44d7eb87`.

## Container execution

Author-only fixtures were copied into fresh verifier containers as `/app`.
The real `/tests/test.sh` performed privilege reduction, initialization,
full-batch invocation, output validation and finalization. Containers had no
network and no API credentials; only the Qwen smoke run used GPU 0.

| Fixture | Deterministic result |
| --- | --- |
| Genuine untuned Qwen3-Embedding-0.6B retriever | Valid; nDCG@10 = 0.0042472591 |
| Empty ranking for every query | Valid; nDCG@10 = 0 |
| Missing output | Rejected |
| Duplicate document IDs | Rejected |
| Missing query outputs | Rejected |
| Nonzero query exit | Rejected |
| Attempts to read hidden labels/grader or write reward/read-only app | All denied |
| Valid output written, then process exceeds deadline | Rejected at 120.000095 s |

The genuine retriever freshly encoded all corpus documents during build,
loaded its resident model and then encoded every hidden query. Build took
**34.5632 s**, and the complete **778-query** invocation took **2.11765 s**.
This validates the interface and feasibility of the time budget for this
baseline; it does not establish the best attainable quality or difficulty.
The earlier 1,146-candidate nDCG/latency results describe a different split.

Every fixture's final audited reward was **zero**, as expected without required
judge credentials. The positive raw score above is from deterministic retrieval
grading, not a successful model audit. The fail-closed finalizer also has direct
tests for a passing judge and for malformed/missing/failed judge results.

Full evidence and author-only fixtures are outside the package at
`task_development/chunqiu-temporal-retrieval/validation/`, including
`container-checks-20261014T134832Z`, `evidence.json`, image build logs and the
instruction/data audits in the adjacent construction directory.

## Remaining validation and publication

No coding-model identity, reasoning effort, agent trajectory, trial score or
live judge result is claimed. The repository
[creation skill](../../.agents/skills/create-searchswe-task/SKILL.md) requires:
“Validate the setting with an actual configured coding-model run as well as
grader checks.” That additional paid validation has not been authorized or
performed in this local delivery. A future run needs a user-selected coding
model and its provider credential, plus `VERIFIER_OPENAI_BASE_URL` and
`VERIFIER_OPENAI_API_KEY` for the required audit. Optional submission APIs use
`OPENROUTER_API_KEY` / `JINA_API_KEY`. Configure values locally, never in Git.

Remote embedding/LLM latency has not been measured under the 120-second budget.
No active-PR collision review, dataset publication, commit, push or PR was made.
The three data revision pins and source-page attribution review remain release
prerequisites. No difficulty claim is based solely on this untuned baseline.
