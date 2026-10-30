# Join-aware table retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `join-aware-table-retrieval` |
| Version | 1.0.0 |
| Authors | Bingyu |
| Primary metric | Complete table-and-join coverage at 5 tables and 6 joins |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 4800 s |
| Hidden queries | 10 |

Build a CPU search engine over 1,056 tables in 206 opaque database groups. Given a natural-language question without a database ID, return exactly five tables and at most six public column-level equality relationships. A question scores one only when an acceptable table-and-join plan is completely covered. The task score is the mean over all hidden questions. Author: **Bingyu**.

### Corpus and runtime

The catalog contains 935 public relationships and 2,926 sample rows, at most three per table. Original semantic table and column names remain visible; table and database identities use persistent opaque IDs. The catalog is byte-identical to versions 0.4.0 and 0.5.0: SHA-256 `d2231b44cf71f2e618fbe8bbe2b3a3664220154f079fb4f96f564c6fa25a6ac4`. No catalog descriptions, rows or joins were edited to fit the new questions. Earlier uniform description and compound-primary-key repairs remain in place. Multiple `primary_key: true` columns jointly form a compound key.

Both images use `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0`. Resources remain 16 CPUs, 32 GiB RAM and no GPU. Build/readiness/scored-response limits are 1,200/30/20 seconds, with an 8 GiB index. Coding and whole-verifier budgets remain 7,200 and 4,800 seconds respectively. Queries are sent individually; time cannot be pooled across questions.

The agent starts with an empty `/app/submission`; only that directory transfers to a fresh verifier. The verifier builds a new index and runs submitted commands as UID 10001. Hidden questions, labels and reward files remain protected. One synthetic warm-up precedes scored work. This revision fixes an earlier recovery bug: a warm-up failure is recorded, the process is restarted, and the actual query still receives its own full deadline instead of losing a point before it was sent.

The CPU/API resource documents remain byte-identical to `tasks/agentic-search`. OpenRouter/Jina retrieval APIs and the four listed Qwen generation models remain available during indexing and queries. The archived newer engine uses Qwen 3.5 for query-time selection; Luna is the coding-agent model, not the retrieval model used on every query.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

### Difficulty evidence and its limits

Selection uses the two unchanged programs produced in the earlier Codex/OpenRouter `openai/gpt-6-luna`, `max` trials, plus three fixed lexical baselines. Every test question has a recorded wrong response with available API output in **both** archived programs. API failures and timeouts alone do not qualify. The older program additionally needs a timestamp-aligned returned selector dictionary to count as a confirmed API response.

All three lexical baselines fail all ten test questions. Nine selected questions have no observed success in either archived implementation. One has an earlier success in the newer implementation, followed by two confirmed retrieval failures; that counterexample is retained. These observations establish weaknesses in those implementations, not that no future solver can answer the questions.

| Fixed lexical baseline | Validation | Test |
| --- | ---: | ---: |
| Independent-table BM25 | 0/10 | 0/10 |
| BM25 with database grouping | 1/10 | 0/10 |
| BM25 with join-graph search | 1/10 | 0/10 |

The final selected subset of the 20-second confirmation run scored **0/10 for both archived programs**. The newer program had nine confirmed retrieval errors and one timeout; its completed-response mean was 16.53 seconds. The older program had seven confirmed retrieval errors and three API fallbacks; its completed-response mean was 7.86 seconds. Those fallbacks remain in the denominator, and earlier healthy failures supply the separate semantic evidence for those questions.

Two timeout-only candidates received an explicitly separate, non-scoring 60-second diagnostic. The advisor question answered correctly in 18.74 seconds and was excluded. The selected instructor-appointment question returned a wrong answer in 10.86 seconds. The task itself retains its 20-second limit. A separate one-question selector check still suffered an API failure; that candidate was excluded rather than credited as a semantic failure.

The subset scores above were used for selection and are **not an independent estimate of performance**. After freezing the final package, one fresh Harbor Codex/OpenRouter `openai/gpt-6-luna`, `max` coding trial completed with **1/10 hidden success (0.1)**. All ten predictions were valid and arrived within 20 seconds: mean **3.74 seconds**, maximum **5.26 seconds**. Eight failures lacked a necessary table; one covered the tables but missed a required relationship. There were no query timeouts, warm-up failures or server stderr messages. Raw HTTP responses were not captured, so empty stderr establishes absence of logged API failures, not a separate HTTP-level audit.

The fresh program used one Jina table-reranking request followed by local five-table subset and join-graph search, with a local fallback. It made no Qwen generation calls at query time. Its final public development self-tests scored 10/10 both online and offline; the checker was reviewed, but raw predictions were not saved and the development script did not enforce the wall-clock deadline. These are development scores, not an independent validation replay.

The fresh program solved `shipment_header_and_item_orders`; the earlier success on `municipal_occupancy` remains in the evidence. Consequently **eight of ten** have never been observed solved across all three programs, and the fresh program failed nine. This ten-question challenge has measured difficulty, not a claim that every question defeats every implementation. The full result is in `task_results/join-aware-table-retrieval/codex-openrouter-gpt-6-luna-max-v060-20261014-232013/REPORT.txt`, with per-query records in `query-results.json`. The requested model and effort were verified from the actual session. No score-based rerun occurred. The original evaluated revision and fingerprints are retained in the validation records.

[VALIDATION.md](VALIDATION.md) consolidates the trial ID, UTC timestamps,
instruction fingerprint, configured budgets, raw/final scores and original
evidence locations. The 2026-10-22 reconciliation confirmed that all 23
non-README files in the frozen run manifest still match. This existing trial is
reused without rerunning the coding agent. No model judge is configured for this
task; the HTTP-observability limitation above is retained.

## Verification Explanation

### Evaluation split and query limits

The task contains **10 public validation questions and 10 hidden test questions**. Each scored response has **20 seconds of wall-clock time, including API calls**. A timeout scores zero for that question and leaves every question in the denominator. The verifier may restart the search service for subsequent questions.

| Split | Questions | Database groups | 3-table plans | 4-table plans | 5-table plans | 2 / 3 / 4 / 5 / 6 required equalities |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Validation | 10 | 9 | 0 | 0 | 10 | 0 / 0 / 4 / 2 / 4 |
| Test | 10 | 7 | 1 | 1 | 8 | 1 / 0 / 3 / 2 / 4 |

All 20 table-and-join structures are distinct. Database and schema-family overlap is allowed; this is a performance-conditioned challenge, not a database-held-out benchmark. Public examples require multiple semantic roles, bridge tables or composite relationships. Full databases, author SQL, identity mappings, selection scripts and baselines are not supplied to the coding agent.

Every selected question has an executable, nonempty SQL witness and a manual review of its requested fields, table roles and public relationships. Checks cover declared columns, positive scoring, missing tables, missing equalities, wrong-role edges and alias-aware equivalent edge replacements. These checks support the labels; they are not an exhaustive proof of every possible SQL equivalence. Repeated aliases share a base table ID, while distinct required column equalities remain separate.

### Earlier validation sets

| Validation set and measurement | Old archived program | New archived program |
| --- | ---: | ---: |
| Original 10 questions, current 20-second replay | 8/10 | 0/10 |
| Previous 20 questions, earlier 60-second measurements | 13/20 | 20/20 |

The original-10 replay had API warnings on four old-program questions and two new-program questions, plus three new-program timeouts. Its repeated question structures are not counted as independent difficult cases. The earlier old-program 20-question measurement had seven API warnings. The newer 20/20 consists of coding-agent development predictions subsequently rescored with the formal scorer; it was not an independent held-out replay. Different deadlines and provenance prevent treating these rows as a controlled score comparison. Detailed evidence is in `hard-v060/historical-validation-comparison.json`.

### Author records and reproduction

The frozen source of the split is `task_development/join-aware-table-retrieval/hard-v060/selection.json`. `combined-evidence.json` retains successes, healthy errors, infrastructure failures, deadlines and source paths. `selected-confirmation.json` contains the selected retrospective subset; `selected-baselines.json` contains all lexical outputs. The complete pre-change package and its historical README are preserved in `package-build/revisions/pre-hard10-0.5.0/task/`.

From the development directory, export and check the frozen selection:

```bash
python -B scripts/package_challenge_v060.py
python -B scripts/evaluate_v060_baselines.py
python -B scripts/audit_v060_questions.py --out hard-v060/final-audit
```

The audit includes SQL, scorer, split, local asset and package checks. Author-only Docker fixtures exercise oracle success, per-query timeout, warm-up recovery, missing joins and isolation. Their reports are stored under `hard-v060/runtime-checks-final/`. Historical exporters are not the reproduction path for this revision.

From the repository root:

```bash
python scripts/download_assets.py --task join-aware-table-retrieval --verify-only
python scripts/check_tasks.py tasks/join-aware-table-retrieval
```

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task join-aware-table-retrieval
bash scripts/run_task.sh --task join-aware-table-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max
```

## References

### Attribution

Source: [Spider 1.0](https://yale-lily.github.io/spider), by Tao Yu and collaborators, under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The captured official archive has 205,800,266 bytes and SHA-256 `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`. Attribution and adaptation details are in `LICENSE.data.md`.

- [Task reference](https://arxiv.org/abs/1809.08887).
