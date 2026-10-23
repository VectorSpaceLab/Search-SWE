# Local validation record

Release reconciliation (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md) records the available Luna result, judge health, version limits and published asset pins. The records below preserve earlier validation stages; statements that no trial has run, a trial is running, or assets are unpublished refer to those earlier stages.

Current revision: v0.3.0. The corpus expansion is installed and the frozen Luna
submission has been replayed through the actual grader. Raw results are 0/10
public and hidden with original short waits; 0/10 public and 2/10 hidden with
query waiting limits removed. No new coding-agent Harbor trial or paid trajectory
audit was run. Historical configured-model evidence below remains intact.

## Revision v0.3.0: corpus expansion and frozen replay (2026-10-14)

The corpus contains 8,011 passages: 3,907 unchanged originals plus 4,104 additions.
Of those additions, 3,889 cover 346 background cohorts and 215 cover 19 evaluated
subject cohorts. Corpus rows are independently reshuffled; IDs have the same
opaque 32-hex format. Public records still contain only `doc_id,text`. Author
provenance, generation jobs, seeds, review corrections and hidden labels are not
introduced into Agent mounts. Queries, labels, gold texts, instruction, grader,
4-CPU resource profile and 8-second timeout contract are unchanged.

Local Qwen3.5-9B produced 4,405 candidates. Filtering removed 301 truncations,
duplicates or sampled unsupported details. Eight passages received source-based
father/son disambiguation. Each admitted evaluated-subject passage retains an
affirmative exclusion fact; all original matching candidates were previously
reviewed, so the 20 unique positives remain unchanged. Every evaluated cohort
was sampled and the Canale and Double Bay issues received extra review. This is
not exhaustive factual certification of generated prose or independent human
annotation. The source, correction and rejection ledgers are author-only.

Hidden gold RRF ranks shift from median 2 to median 11.5; Top-8 recall drops from
10/10 to 2/10. Always choosing rank 2 drops from 9/10 to 0/10. Full-query BM25
with Luna's tokenizer and b=.75 has hidden median rank 12.5 and Recall@8 2/10.
These are matched before/after protocols, separate from historical screening.
The data and review decisions were frozen before measuring either rank or API
outcomes; no score-dependent retry or corpus retuning followed the replay.

The replay uses the frozen final `/app` from the v0.2.2 Codex + OpenRouter
`openai/gpt-6-luna`, effort `max`, trial. The program calls
`qwen/qwen3.6-35b-a3b` with its original prompts, max_tokens=100 and reasoning
disabled. Each split runs once in each condition (40 API requests total), with
4 CPUs, 32 GiB, UID 10001, read-only submission and private verifier data. The
cached v0.2.2 verifier image is used with the current unchanged retrieval grader
mounted in; the paid audit entrypoint is not called. The 8s copy changes only
observational logging. The unlimited copy additionally removes the HTTP timeout,
thread join timeout and grader query deadline, retaining the build deadline.
All 20 pairs of API payloads match exactly, and reversing documented diagnostic
edits reproduces the frozen solver byte-for-byte.

| Condition | Public | Hidden | Grader query timeouts |
| --- | ---: | ---: | ---: |
| Original short waits, 8-second grader | 0/10 | 0/10 | 0 |
| Query waiting limits removed | 0/10 | 2/10 | 0 |

Eight hidden gold passages never reach Qwen. The two recalled Avery queries
both log ReadTimeout at the program's 2.6-second read limit in the original
condition, then succeed in the unlimited replay. All unlimited test calls take
3.007–6.805 seconds including process startup and retrieval, still below 8 seconds.
Public Mowat is recalled but Qwen selects a wrong marriage-containing passage.
All 20 unlimited API responses are HTTP 200. Each split has three responses
truncated at the original 100-token cap and two empty-eligibility responses,
all on requests without a gold candidate; those trigger the original fallback.
Calls are sequential at different times and can use different providers, so
this is not a controlled causal estimate of API latency changes.

Executed validation:

- All three runtime asset hashes verify; 22 task unit tests pass.
- Task-scoped release check with local staging and `allow_unpublished=True`
  reports no errors and the expected unpublished-assets warning.
- Strict package check retains exactly three unpublished revision errors.
- Network-disabled correct-answer and permission-boundary container fixtures
  both score raw 10/10. Their deliberately missing audit credentials keep final
  reward zero, as required. They validate grading and isolation, not retrieval.
- The actual replay reports valid output in all four conditions/splits.
- Twenty matched API request pairs and 396 artifact files passed the credential
  scan at analysis time. Full request/response bodies and per-query timing remain
  available without authorization headers.
- Original instruction SHA-256:
  `03a445f6f0bfa8ab8bd51a0ca788a4d1da15190939d2a76c6bd49b39aec0a16c`.
- Expanded corpus SHA-256:
  `5f67d4a41b59554ce9bf7af2add5175ae6a6f9b40dbd85831619c7bce1d4e949`.

Evidence roots in the surrounding workspace:
`task_development/negative-constraint-retrieval/construction/corpus-expanded-v030/`
and `task_results/negative-constraint-retrieval/frozen-luna-expanded-v030-20261014T113140Z/`.
See REPORT.txt, rank-comparison.json, subject-candidate-audit.json, text-review.json,
augmentation-ledger.jsonl, config.json, summary.json, per-query.json and raw API logs.
Early author generation mistakenly used GPU 1; after the user's restriction that
worker was stopped and only GPUs 6/7 were used. Both authorized GPUs were confirmed
released afterward. No other user's process was terminated.

Remaining release evidence: an independent fresh coding-agent trial on v0.3.0,
redistribution rights and immutable published asset revisions. Generated-style
shortcuts have not been exhaustively excluded. These limitations do not negate
the completed frozen-program replay, but it is not a new audited Harbor result.
The old prepared v0.2.3 regrade targets old asset hashes; it must not be silently
retargeted to this changed corpus.

## Revision v0.2.3 and configured-model evidence (2026-10-14)

One user-authorized Harbor 0.22.0 trial ran Codex 0.157.1 through OpenRouter with
`openai/gpt-6-luna`, reasoning effort `max`. The actual session metadata confirms
model, provider and effort. It ran v0.2.2's frozen instruction and task files in
the right pane of Herdr session `bingyu`, window named `3`. Source hashes were
unchanged during the run; both Agent and verifier containers had 4 CPUs and
32 GiB RAM. There was one coding-model trial and no whole-trial retry.

The submission built in 1.063 seconds. All 10 hidden invocations completed with
valid output and no verifier timeouts: one correct, nine wrong, raw Accuracy@1
0.1. Query latency was 3.318–5.032 seconds, median 3.718, mean 3.980, cumulative
39.796. Agent development took 115.063 minutes. Its public self-tests scored
10/10 in roughly 1.0–1.2 seconds per query. No hidden answer was supplied to the
Agent and no wording was retuned using the score.

Harbor reports one completed trial and no trial exception, but final reward is
0.0 and `judge_succeeded=false`. The first DeepSeek audit's native session
returned score 1. Its process log contains a transient `Reconnecting...` error
followed by `turn.completed`. RewardKit 0.2.0 retains that error even after
successful recovery, so it launched a second audit and exhausted the outer
1,200-second deadline before recording a valid accepted decision. The original
reward/result files remain intact. This is not a valid final zero measuring
retrieval ability. Coding-agent transport recovery is separate: two recovered
stream events and 26 nonfatal model-catalog refresh timeouts were observed.

A post-hoc diagnostic in a network-disabled verifier image used the frozen
submission without invoking its API path. Candidate recall was 10/10 on both
splits, but its local rules recognized all 10 public requests and none of the
hidden requests. Its local fallback scored 10/10 public and 0/10 hidden; all
hidden requests enter the API path when a key is present. Nine actual hidden
answers equal that fallback. The submission silently handles API/parse errors,
so matching predictions do not prove why it fell back or whether an API also
selected the same document. Its own API deadlines are 2.6 seconds for connect
and read, with a 4.3-second thread wait, below the verifier's 8-second allowance.
The run therefore shows a selection/generalization problem, without identifying
the exact internal API failure contribution. It does not isolate the causal
effect of wording from other setting changes or model/API variability.

v0.2.3 adds the task-local `rewardkit_transport.py` launcher. It clears only
recognized reconnect events followed by a completed turn with no other error or
failed turn, retaining the original diagnostic as a warning. RewardKit's
nonzero-exit, missing-response and structured-output checks remain in place;
the judgment text is never changed. The shared DeepSeek wrapper remains
byte-identical to other tasks. No query, label, instruction, retrieval grader,
judge criteria, resource limit or timeout policy changed.

Executed checks for this repair:

- All 22 task unit tests passed, including eight new transport regression cases.
- Shared RewardKit tests: four passed, two skipped for the absent host dependency.
- The actual saved failing process log was replayed through the real RewardKit
  0.2.0 backend in a network-disabled container. The original failure reproduced;
  the repaired backend accepted the same completed judgment, while nonzero exits
  remained rejected. There were zero API calls in this regression replay.
- Shell/Python syntax checks passed. The strict package check reports only the
  same three existing unpublished-asset revision errors; no revision was invented.
- An attempted build of the actual v0.2.3 verifier Dockerfile with networking
  disabled missed the dependency cache and was stopped. It is not recorded as a
  successful image build. The backend replay used the existing v0.2.2 image with
  the new compatibility module mounted read-only.

The prepared Harbor regrade copies the original artifacts and trajectory into a
new separate verifier trial; it does not rerun Codex or overwrite the original
trial. Automatic approval review rejected its launch because it considered the
additional paid external processing of the saved submission/trajectory to need
explicit approval. That approval remains pending; no regrade has started.

Evidence root in the surrounding workspace:
`task_results/negative-constraint-retrieval/codex-openrouter-gpt-6-luna-max-v022-20261014T064718Z/`.
See `REPORT.txt`, `analysis-summary.json`, `verification-observations.json`,
`offline-diagnostic.json`, `transport-regression.json`, `regrade-metadata.json`,
the original `jobs/2026-10-14__14-48-16/negative-constraint-retrieval__8rttgWz/`,
and `judge-session-evidence/`. Harbor reports Agent cost USD 0.250323975; this is
not a complete provider bill and excludes separately unmeasured task API/audit
costs. No publication, push or PR was performed.

## Revision v0.2.2 (2026-10-14)

All 10 validation and 10 hidden queries were rewritten again. The previous
wording repeatedly asked for the subject to be named and explained that a
violation made the passage unsuitable. The new wording uses conversational
questions, reading preferences, context and references across sentences, while
retaining the exact exclusions and permitted exceptions. Average query length
falls from 41.8 to 33.1 whitespace-delimited words.

The shared requirement to name each requested subject, with surnames sufficient
for people, now appears once in both instructions rather than in each query.
Both instructions also explain that requests to leave content out, including
personal preferences, remain exclusions. Semantic equivalence is assessed using
the query together with this shared contract, not the query in isolation. The
source-to-request audit maps the new paragraph under raw Task Description to
paragraph two of the natural instruction. All other instruction text is
byte-identical to v0.2.1. No new positive-document clues were added.

The assistant author read all 47 query/candidate combinations in full, including
the long Mowat passages and all four negatives for each of the two literary and
musical queries. The full-corpus subject-name scan matches the reviewed candidate
sets exactly. This is author review, not independent human adjudication or an
automatic semantic proof. All 20 unique positives, labels, query/document IDs,
query order, subject-disjoint 10/10 split and corpus bytes remain unchanged.
The grader, 8-second deadline, 4 CPUs and per-query timeout scoring are unchanged.

Executed checks:

- `construction/natural-language-v3/audit_revision.py`: all 20 rewrites differ
  from v0.2.1; candidate coverage, corpus/label/ID/split invariants and unchanged
  grader/resource files passed. Reapplying the rewrite helper is idempotent.
  `freeze_task_dataset.py` still calls that helper and therefore uses v3 wording.
- Runtime asset verification passed for all three files. Public-query sizes and
  hashes were refreshed in the asset manifest and local HF staging. The scoped
  release check with data verification and `allow_unpublished=True` has no
  errors and one expected unpublished-assets warning.
- `probe_rewritten_queries.py` ran without APIs on all 3,907 documents after
  freezing the rewrite ledger. Current BM25 hits: 0/10 validation, 0/10 test.
  Archived luna's local fallback, with generation disabled: 3/10 validation,
  0/10 test; candidate recall at 8: 8/10 and 7/10. Previous wording reproduced
  BM25 1/10 and 0/10, fallback 2/10 and 0/10, recall 10/10 and 8/10. These are
  lexical diagnostics, not a new luna trial or proof of increased difficulty.
  No wording was selected or retuned using these scores.
- Rebuilt the actual verifier Dockerfile as `search-swe-local:nc-v022-verifier`,
  image config digest
  `sha256:968aa3fbd79830a6fad2c5e6ce3605742b4d9efde19d2953fb451aa36f291888`.
  A network-disabled container confirmed the bundled hidden-query SHA-256 is
  `dcbc1ed14746ffc27850ebeb8d581b76acfe2c05f2225017add2c984d86b25e2`.
- One correct-output fixture ran through the rebuilt verifier with 4 CPUs and
  networking disabled: all 10 queries processed, valid output, raw score 1.0.
  The intentionally unconfigured trajectory judge kept final reward zero.
  This fixture tests packaging/interfaces, not genuine retrieval. The 14 unit
  tests and 12 broader container checks below belong to v0.2.1's unchanged
  grader and were not unnecessarily repeated for the wording change.
- Modified Python/TOML syntax, instruction correspondence, whitespace and
  dataset manifest checks passed; unrelated worktree modifications were preserved.

Evidence is in the author workspace's `construction/natural-language-v3/`:
`rewrites.jsonl`, `evidence.jsonl`, `subject-candidate-audit.json`,
`audit-summary.json`, `offline-probe-summary.json`, `container-checks/`,
`release-check.json` and `revision-hashes.json`. Previous task files and author
scripts are preserved in `before/` and `before-author/`.

Current instruction SHA-256: `03a445f6f0bfa8ab8bd51a0ca788a4d1da15190939d2a76c6bd49b39aec0a16c`.
Current grader SHA-256: `e249a18bcc6ba522f6420d4b09e1be0dbdca6d1ac3fe442f4d91fb52b3051a95`.
At the wording freeze, a new coding-model trial and live audit had not yet run.
The subsequent authorized trial and its audit-infrastructure failure are recorded
above; the older luna score must not be attributed to this revision.

The following records describe earlier revisions.

## Revision v0.2.1 (2026-10-14)

Each query now has an 8-second total wall-clock deadline (3-second base budget
plus a fixed 5-second network allowance). A query timeout contributes zero for
that query, ignores any output it wrote, and does not stop subsequent queries.
Accuracy@1 divides successful hits by the full query count, including timeouts.
For example, nine hits and one timeout score 0.9; seven hits, one wrong answer
and two timeouts score 0.7. The trajectory audit remains a required gate. Build
failures/timeouts, non-timeout command failures, invalid completed output and
integrity violations retain the existing whole-submission failure policy.

Timeout cleanup terminates the current query process group while preserving
build-started services for later queries. Every query receives distinct input
and output paths to isolate late responses. Global submission cleanup still
runs when evaluation ends. The report records each timeout, the total timeout
count and every query's elapsed time and exit status. Reported timeout elapsed
time includes process cleanup after the 8-second deadline; cleanup does not
extend the time allowed for a scored answer.

The structured instruction, natural instruction, environment document, README
and author task definition were aligned with this contract. The 4-CPU quota,
zero GPUs, build budget, interfaces, corpus, rewritten queries, labels, split
membership and asset manifest are unchanged from v0.2.0. The CPU quota is not
an API concurrency limit.

Executed checks:

- Task-local unit suite: all 14 tests passed. Coverage includes continuation
  after a timeout, ignoring correct output from a timed-out invocation, all
  queries timing out, distinct paths, and a 2/3 score surviving the finalizer
  with a mocked passing trajectory audit.
- All 12 disposable-container fixtures passed with 4 CPUs and networking
  disabled. Correct and permission-boundary fixtures scored raw 1.0; one wrong
  answer scored 0.9. First-query timeout, second-query timeout and timeout with
  a persistent build service each scored 0.9. The mixed two-timeout/one-wrong
  fixture scored 0.7. All timeout fixtures processed all 10 queries, ignored
  correct output written before the timeout, and checked that timed-out child
  processes were no longer live. The service fixture checked that its build
  service survived. Missing output, duplicate output, unknown document, build
  failure and missing second output remained invalid with raw score zero.
- Container fixtures deliberately omit online-judge credentials, so final
  rewards remain zero and the judge fails closed. The fixture raw scores and
  unit-tested passing-audit finalization together validate timeout scoring;
  these are not coding-model trials or successful live audits.
- Verifier image built from the actual task Dockerfile:
  `search-swe-local:nc-v021-verifier`, config digest
  `sha256:180583b10268b9907898451c659b81093c41a94c8484ac488bd8d3d8fd913f39`.
- Runtime asset verification passed for all three files. Task-scoped release
  checks with `allow_unpublished=True, verify_data=True` returned zero errors
  and the expected unpublished-assets warning. Immutable publication revisions
  remain unavailable; no release pin was fabricated.
- Python/shell syntax, documentation consistency, dataset byte invariants and
  whitespace checks passed. Unrelated repository modifications were preserved.

Evidence and pre-change files are retained under the author workspace's
`construction/per-query-timeouts-v021/`, including
`container-checks/summary.json`, individual evaluations and
`revision-hashes.json`.

The earlier user-authorized synthetic API probe completed 23 of 30 single-call
retrieval flows within 8 seconds. This is a small latency sample, not a model
accuracy measurement or a guaranteed service latency. It used synthetic data
and the existing host proxy, not the unpublished task data or Harbor's gateway.
Its evidence is in `construction/api-latency-synthetic-20261014/`. No new API
calls or luna trial were run for v0.2.1.

v0.2.1 instruction SHA-256: `5798bcaf6faafd4665e64c3feb8474f8b91ba247121f6b8503b567621802a232`.
v0.2.1 grader SHA-256: `e249a18bcc6ba522f6420d4b09e1be0dbdca6d1ac3fe442f4d91fb52b3051a95`.

The records below are historical and preserve the earlier behavior and budgets.

## Revision v0.2.0 (2026-10-14)

The user confirmed a per-query deadline of 5 seconds (3-second base budget plus
2-second fixed network allowance). Local compute changes from 16 to 4 CPU cores;
GPU count remains zero. The verifier builds once, then reveals and runs one
query at a time. Startup/index loading and all API waits/retries count toward
that deadline. Unused time cannot be pooled. A timeout keeps the established
execution-failure policy of zero overall reward. Background services and the
index can persist between successful invocations. CPU quota does not cap API
concurrency. Each query's timing and exit status are retained in `evaluation.json`.

All 20 queries were rewritten into varied natural language, retaining the
subject-name requirements, hard exclusions, allowed exceptions and unique
labels. Some exclusions precede the subject; others use preferences, anaphora
or interleaved allowed content. Equivalence was reviewed against the complete
positive and all subject-matching negative passages. This is assistant author
review, not independent human adjudication. Corpus bytes, all query/document
IDs, labels, ordering and 10/10 split membership were checked unchanged. Runtime
asset and local staging hashes were refreshed. Author evidence is under
`task_development/negative-constraint-retrieval/construction/natural-language-v2/`:
`rewrites.jsonl`, `evidence.jsonl`, `revision-hashes.json`, `offline-probe*.json*`
and `container-checks/`. The original task files are retained under `before/`.
`freeze_task_dataset.py` reapplies the reviewed rewrites after freezing original
screening evidence; `rewrite_task_queries.py` is deterministic and idempotent.

Source-to-request audit: the structured and natural instructions agree on the
single build, singleton sequential query invocation, 5-second total deadline,
fixed allowance, no budget pooling, persistent index/services, hidden-query
visibility, 4 CPUs and zero-on-timeout policy. Existing CLI flags, result schema,
Accuracy@1, corpus restrictions, model allowlist, credential rules and artifact
transfer remain intact. Environment docs expose the same contract. The existing
`tasks/reasoning-query-rewriting` structural precedent remains applicable; this
revision introduces no new shared runtime or API profile.

Executed checks:

- `python -m unittest discover -s tasks/negative-constraint-retrieval/tests -p 'test_*.py'`: 11 passed, including per-query deadlines, stopping after timeout and rejecting stale output.
- `python scripts/download_assets.py --task negative-constraint-retrieval --verify-only`: all 3 runtime assets passed.
- Task-scoped `check_release(..., allow_unpublished=True, verify_data=True)` against the existing local HF staging: zero errors, one expected unpublished-assets warning.
- `python scripts/check_tasks.py tasks/negative-constraint-retrieval`: exactly the same 3 pre-existing unpublished-revision errors; no fabricated HF pins.
- Repository image test: 1 passed; network-policy tests: 14 passed; RewardKit tests: 4 passed, 2 host dependency skips. These targeted checks supplement the earlier full-suite record below.
- Shell syntax, modified Python syntax, instruction/interface review, asset invariants and whitespace checks passed.
- `docker build -t search-swe-local:nc-v020-verifier tasks/negative-constraint-retrieval/tests`: succeeded from the actual Dockerfile, reusing pinned dependency layers. Image config digest: `sha256:d610bf31dde4f5dfe2c094ce9b8b469764fd862db40d146114b93a0edb04f652`. An initial `--network=none` build missed the dependency cache and was stopped after offline DNS retries; the normal build reused the cache. No dependency or image definition was changed. The Agent image/build context is unchanged.
- `python task_development/negative-constraint-retrieval/scripts/validate_task_containers.py` from the parent workspace: all 10 disposable-container fixtures passed, each with 4 CPUs and networking disabled. Correct and permission-boundary fixtures scored raw 1.0; one-wrong scored 0.9. Missing output, duplicate rows, unknown document, build failure, first-query timeout, second-query timeout after a fast first query, and missing second output all failed as expected. Successful runs contained 10 separately timed invocations. Fixtures verify no hidden query is staged during build. The required online judge was deliberately unconfigured, so final rewards correctly remained zero; these are grader fixtures, not coding-model runs or solutions.

The offline lexical probe uses the original fixed BM25 screening protocol on
all 3,907 documents. Original wording: 0/10 public, 0/10 hidden; rewritten:
1/10 public, 0/10 hidden. Separately, the archived luna implementation's local
fallback (without any API calls) changes from 3/10 public and 3/10 hidden to
2/10 public and 0/10 hidden; hidden candidate recall at 8 changes from 10/10 to
8/10. These are diagnostics of frozen rewrites, not selection criteria. No
rewrites were tuned using these scores. Dense/reranker scores and the old
four-baseline 0/20 claim have not been remeasured for the new wording.

Historical configured-model evidence: `openai/gpt-6-luna`, effort `max`, one
completed trial with no Harbor errors, raw/final score 0.8, required trajectory
judge score 1, build 0.416 seconds and complete batch 59.049 seconds. Its result
and trajectory are in
`task_results/negative-constraint-retrieval/codex-openrouter-gpt-6-luna-max-20261013T090647Z/jobs/2026-10-13__17-07-07/negative-constraint-retrieval__ocQY3Rq/`.
That run exercised v0.1.1's original wording, 16 CPUs and 900-second batch budget;
it does not validate v0.2.0. A fresh paid luna/max run with the final revision
and a valid live judge is still required to measure the revised difficulty.
The skill's model-evaluation layer remains pending scoped authorization;
credentials were not probed and no new paid calls were made.

v0.2.0 instruction SHA-256: `f8585098b96f4a956534e2f91b734327a714d1a753b5ec27042c569e17296c5d`.
v0.2.0 grader SHA-256: `95cdddad72c9041bb3e015e4c96a062eb48f081271e2c8d8c16b28f386a5cde9`.
All remaining hashes are in the author-side `revision-hashes.json`.

The records below describe earlier revisions and retain their original budgets,
hashes and unperformed-validation status at the time they were written.

## Revision v0.1.1

`raw-instruction.md` now follows the section order of the existing
`reasoning-query-rewriting` task. Both task environments use the shared
`${OPENROUTER_API_KEY:-}`, matching `agentic-search`. The supplied implementation
and its image COPY/chmod steps were removed; the Agent implements the engine
under `/app`. Dataset, interfaces, budgets and grading remain unchanged.

This revision passed the six task-local contract tests, heading-structure and
TOML checks, shell/Python syntax checks, and whitespace review. The rebuilt
Agent image was checked to contain an empty `/app`. Static package validation
still reports only the same three unpublished asset revisions. Earlier container
fixtures and repository regression results below are historical v0.1.0 evidence;
the unchanged grader remains covered by the current contract tests. No configured
coding-model trial was run for either revision.

## Natural request wording update

At the user's request, the Agent instruction now follows the simpler narrative
of `reasoning-query-rewriting`: data paths and purposes replace corpus counts,
input field inventories and construction details. Exact API rules are incorporated
through the existing resource document. The structured source was aligned and
the contract audit refreshed. Paths, output contract, budgets,
permissions and scoring behavior remain unchanged. Checks were limited to
manual equivalence, required interface/limit presence, section structure and
whitespace; no runtime tests or model runs were repeated for this prose edit.

A subsequent formatting request added multi-line Bash examples for build and
query invocation, plus a separate JSONL output example. Both commands match the
structured source and pass shell syntax checks; the output example parses as
JSON and matches the source. This formatting change preserves every interface
argument and requirement.

The latest rewrite follows the reference's complete narrative structure, placing
retrieval integrity with the data and simplifying the submission and evaluation
paragraphs. At the user's request, hardware allocations, Agent/build/query
budgets and detailed verification-container behavior now live in the required
Agent-visible environment document. Their values agree with task.toml and the
grader. Command and JSON examples were rechecked against the unchanged raw
source; no runtime or model tests were repeated for this documentation edit.

## Output-file restriction removal

At the user's request, both instructions and the grader no longer impose a
regular-file/no-symlink requirement or a 4 MiB output cap. Output is still read
and validated as JSONL with the existing query coverage and result schema.

`python -m unittest discover -s tasks/negative-constraint-retrieval/tests -p 'test_*.py'`
passes all eight tests. They include valid symlink output and valid JSONL larger
than the former limit, as well as missing/malformed output, coverage, result
validation and reward/audit behavior. No image rebuild or container/model run
was performed for this change. The recorded verifier image and older container
checks below predate this grader revision.

## Fixed revision

- `instruction.md`: SHA-256 `89e2137add921abfd1750041f34e1192cf858d3e0753db164b7be8eec47f252a`.
- `raw-instruction.md`: SHA-256 `bce7e438108f8837d5d335e95f6141abf617557534e62ddc4fd88b8177cfdf59`.
- `environment/docs/environment.md`: SHA-256 `be1fe41e43a40008764ecc80ef8ffa67c57b136007f74186de5a4480ce2e4587`.
- `tests/grader.py`: SHA-256 `8d6b1831f81d1e40be9fe5ef3735979354059c221fb9c7e8d35fa99288a8850b`.
- Public corpus: SHA-256 `c77bbda0a5b5cc1720f75f3195d1578f03dca18210ae8be812a19c724bd97c4d`.
- Agent image `search-swe-local:nc-agent`: `sha256:0890e6b6437d7a761ea370ff1d2a7219f69ed58caab4dbb9d746623ce00e749c`.
- Verifier image `search-swe-local:nc-verifier`: `sha256:489ee03d7d7b9ce1c18edde931a9ebaa1f30a03ae8c9b097102a08906d5cca7b`.

Both images were built from their actual task Dockerfiles. The source-to-prose
manual audit covers all request conditions and is retained at the author
workspace's `construction/final-20/instruction-audit.md`. The user-facing request
uses natural prose with Bash and JSON examples as explicitly requested by the user. Structured source and review notes
are absent from Agent mounts/build context.

## Dataset and baseline checks

All 3,907 original deduplicated texts are preserved byte-for-byte as strings;
public corpus records contain only `doc_id,text`. IDs are opaque and corpus rows
are shuffled. Twenty unique positives and 10/10 split sizes are asserted.
Neither subjects nor the reviewed subject-candidate document sets overlap
between folds. Henry Avery's two queries remain together. All reviewed positive
versus hard-negative row gaps are at least 48.

The original 17 semantic queries and three new intents retain strictly positive
wrong-versus-gold margins for all four fixed baselines. New rounds 07 and 08
completed every expected reranker pair (3,841 and 2,224) with unique pair keys and
finite scores. Auxiliary prompt pair coverage also passed (1,863 and 2,224).
Final BM25/BGE/Qwen-embedding/Qwen-reranker Hits@1 are each 0/20; auxiliary
constraint-aware reranker is 3/20 (1/10 validation, 2/10 test). Reranker ranks are
within the retriever Top-100 union. No full-corpus reranker or latency benchmark
is claimed. Semantic uniqueness remains author-reviewed annotation, not an
independent human audit.

`python scripts/download_assets.py --task negative-constraint-retrieval --verify-only`
verified all three runtime files. `--dry-run` reports their sizes and unpublished
status. The scoped `check_release` function with the task's local staging,
`verify_data=True, allow_unpublished=True, packages=[task]` returns zero errors
and one publication warning. Ordinary `check_tasks.py` correctly reports three
errors: the three assets do not have published immutable revisions. No checksum
or release pin was fabricated. A full remote restoration was not attempted.

## Runtime and grader checks

Both Compose overlays pass `docker compose ... config -q` with a temporary base
service. `bash -n tests/test.sh` and Git whitespace checks pass.

`python -m unittest discover -s tasks/negative-constraint-retrieval/tests -p 'test_*.py'`
now passes eight test methods with multiple invalid-output and final-reward
subcases. They cover row order, missing/duplicate/unknown IDs, cardinality,
boolean/string/nonfinite scores, missing/malformed output, accepted symlink and
larger output, fractional reward, and unsuccessful/missing audit behavior.

Disposable CPU verifier containers received fresh `/app` copies through Docker
artifact transfer, the read-only corpus and docs, and no API credentials. They
ran the actual `/tests/test.sh`, executing submitted code as UID 10001:

| Fixture | Valid output/execution | Raw Accuracy@1 | Final reward |
|---|---|---:|---:|
| Correct-answer output fixture | yes | 1.0 | 0 |
| One wrong answer | yes | 0.9 | 0 |
| Permission-boundary probe plus correct answers | yes | 1.0 | 0 |
| Missing output | no | 0 | 0 |
| Duplicate query ID | no | 0 | 0 |
| Unknown document ID | no | 0 | 0 |
| Build exits 7 | no | 0 | 0 |
| Unmodified BM25 starter | yes | 0 | 0 |

Every final reward is zero because the required online trajectory judge is
unconfigured; its status 78 is an intentional fail-closed check. These correct
answer tables are author-only grading fixtures, not genuine retrieval solutions
and not evidence of an Agent solving the task. They are absent from the task
package and both image contexts. No positive audit decision was faked. Manual
Docker artifact copying does not replace a Harbor coding-Agent end-to-end run.

The boundary fixture confirmed that UID 10001 cannot read hidden labels,
trajectory or judge environment variables, write reward, or modify `/app`.
An actual 30-second sleeping process was terminated by the same `run_timed`
implementation using a 0.2-second test budget; elapsed time was about 0.92 seconds
including cleanup, with zero live submission processes and zero unreaped
children under Docker `--init`. This tests the timeout mechanism, not a claim
about query latency or a change to the real 900-second query budget.

In v0.1.0, the supplied BM25 implementation completed build/run on all 10 public
queries and the hidden batch with schema-valid output and 0/10 hits in each.
It was removed from the package in v0.1.1 at the user's request; these observations
are retained only as historical checks, not as a current starting implementation.

Initial harness corrections: the permission fixture first omitted a simulated
trajectory file, causing FileNotFoundError rather than testing access denial;
it was supplied before rerunning the affected checks. A first timeout probe
counted terminated zombies as live processes; the corrected probe checks process
state and uses container init. These were fixture issues, not task label edits.

## Repository regression

The final `python -m unittest discover -s scripts/tests -p 'test_*.py'` reports
171 tests, OK with two host skips because RewardKit 0.2.0 is not installed in the
host interpreter. It ran with a 180-second bound outside the network sandbox;
the first sandboxed run stalled during tests using local networking and was
stopped. Test inventories and the documented network-policy table required one
new task entry each. Existing join-aware additions were preserved. Full suite
logs and separate in-image RewardKit checks are retained in the author evidence.
The pinned verifier image subsequently ran all six tests in
`test_rewardkit_deepseek.py` with zero skips, covering the two host-skipped
backend/configuration checks without live model requests.

## Unperformed validation and local handoff

The [create-searchswe-task skill](../../.agents/skills/create-searchswe-task/SKILL.md)
requires: “The configured coding-model trial is a required validation layer,
separate from known-good and negative-case grading.” See its
[validation reference](../../.agents/skills/create-searchswe-task/references/validation.md).
That layer remains unperformed. The launcher preview
`bash scripts/run_task.sh --task negative-constraint-retrieval --dry-run`
stops with `Set --model or AGENT_MODEL`. No selected model/effort, real trajectory,
completed trial score, valid online judge response, API cost or model feedback
exists for this instruction revision. Task APIs are also unprobed.

At initial validation, the checkout had no local `.env` and no required keys
in the process environment.
For a later authorized OpenRouter coding-model trial, configure `AGENT_MODEL`
and `AGENT_OPENROUTER_API_KEY`, plus the required judge's
`VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` and
`VERIFIER_OPENAI_API_KEY` in the ignored checkout `.env`, a supported run-specific
env file, or process environment. Optional submission APIs use
`OPENROUTER_API_KEY` and `JINA_API_KEY`. Preserve any
existing configuration and never share key values in chat or commit them. Model,
effort and scoped paid-run authorization must be established before a live run;
then confirm local configuration is ready and run the skill's bounded probe and
trial workflow. No model-based refinement is claimed in this local version.

Remote PR name collision check, independent human annotation review, upstream
redistribution rights, asset publication/immutable HF pin, remote fresh download,
live API/judge health and configured Agent E2E remain open. Source licensing and
publication are release prerequisites, not claims that local files are absent.
