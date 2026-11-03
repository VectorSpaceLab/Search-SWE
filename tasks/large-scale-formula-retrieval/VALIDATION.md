# API access revision validation

Date: 2026-11-03. Base commit: `c7f8a8064e0ff1be30bca3bf4b42ab6b18e60b03`.

The task still measures formula retrieval quality over the existing corpus and 76 hidden queries. Development and the timed final build may now use the OpenRouter/Jina APIs described in `environment/docs/available_resources.md`; model-weight downloads are prohibited. Loading, warmup and queries remain offline. The user-provided `available_resources.md` was preserved byte for byte.

The reference was `tasks/agentic-search/task.toml` and `tasks/agentic-search/tests/run_submission.py`: reuse the two API hosts, submission credential names and separation from judge credentials. Keep this task's resource limits and restrict API credentials/network access to the build worker in verification.

## Preserved contract

The task retains 2 CPUs, 4 GiB RAM, 64 GiB total storage, no GPU, 7,200 seconds for development, 3,600 seconds for building, 120 seconds for loading, 30 seconds for warmup, 50 milliseconds per query, a 34 MiB prepared-artifact limit and a 40 MiB serving filesystem. Numeric scoring, data assets, storage enforcement, development OOM enforcement and Compose definitions were unchanged.

The initial API-access implementation updated instruction paragraphs 4, 5 and 14 for API permissions, time accounting and credential separation, preserving other paragraphs at that stage. The contributor subsequently rewrote and shortened the instruction. The structured source retains the full policy; the agent-facing instruction remains one source line per paragraph.

Initial API-change instruction SHA-256: `000bd80fb6420efddaa57bef6d9b872821ffe06832a5ce4e185c312129c3b8ad`.

Structured-source SHA-256: `9e35c22f7cf4dedcb1ea3ad8c6b8640c4f25fe1f41e21b8c63736b04d88bf174`.

## Completed checks

- `python scripts/validation/check_tasks.py tasks/large-scale-formula-retrieval`: 0 errors.
- Harbor `TaskConfig.model_validate_toml` and `scripts.egress.config.validate_task_networks`: passed; all task phases declare only `openrouter.ai` and `api.jina.ai` for submission egress.
- From `tests/`, `python -m unittest test_development test_scoring test_ipc_cleanup test_integrity_gate test_api_access -v`: 27 tests passed.
- Disposable Docker container, using the existing `large-scale-formula-retrieval__hz7xygu__verifier__trial-main:latest` image with the current test files copied in: `python -m unittest test_api_access test_runtime -v`, 16 tests passed. The container used 2 CPUs, 4 GiB RAM with no swap, private IPC and `--network none`; the connectivity fixture used loopback only.
- The container checks cover build-only submission credentials and socket access, continued offline serving, hidden-file/reward protection, process cleanup, memory/storage enforcement and timeouts. Dummy credentials were used; judge/coding-agent credentials were excluded from both workers.
- Python syntax, shell syntax, unchanged-budget/resource checks and `git diff --check`: passed.

## Remaining evidence

No live provider request, full-corpus API-assisted build, fresh coding-model evaluation or integrity-model API call was performed for this revision. The container tests validate the worker boundary, not provider availability or a complete Harbor run. Existing model scores belong to the previous resource policy and do not validate the API-enabled setting. See the README's dated checks for historical evidence.

## PR preparation — 2026-11-04

Current instruction SHA-256: `ccb47bcc1b7c813ee2c6814bd7b119cbeb51dda071c17b182c13b34f9d8a57aa`. The current task package passed the static checker with 0 errors. The runtime tests above precede the final prose rewrite; a fresh coding-agent/verifier run remains pending.
