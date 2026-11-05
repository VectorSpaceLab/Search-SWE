# ICSI Meeting Memory Validation — 2026-11-04

## Scope and design

This revision preserves the compact-memory task, its four-file submission interface, 8-CPU/8-GiB CPU environment, five public examples, 143 hidden examples, resource limits and existing score normalization. The task author remains Haoran Jin. Changes are based on repository revision `783d2eeafd580f64c404da94dfc05733811d5c0f` on local branch `bingyu/icsi-review-20261104`.

Structural precedents: `tasks/scientific-paper-qa/task.toml` for the three verifier-only `ANSWER_JUDGE_*` environment variables; `tasks/biomedical-graph-retrieval` for public validation under `data/validation/`; the shared CPU image and the 2026-11-03 agent-docs/workspace-storage audit reports for environment documentation and mounts. No task-specific thresholds, labels or API policies were copied from those tasks.

## Changes and contract review

- Evidence extraction produces one fixed result per question; the submitted answering stage runs once and produces one fixed answer, while retaining its existing allowance of up to two generation calls. Three evidence judgments and three answer judgments assess those fixed outputs. Each paired round scores one only when both judgments pass; the question score is their arithmetic mean. Empty evidence receives zero. An exhausted judge failure invalidates the measurement instead of reducing the denominator.
- Evidence and answer marginal metrics also retain the three-vote means. The existing piecewise score mapping and compliance audit are unchanged. Runtime limits are acceptance boundaries, not latency metrics, so no five-run timing aggregation is applicable.
- Judge model, base URL and API credential come from `ANSWER_JUDGE_MODEL_NAME`, `ANSWER_JUDGE_BASE_URL` and `ANSWER_JUDGE_API_KEY`; no answer-judge model is hard-coded. These values are passed only to the verifier. The separate trajectory-audit configuration is unchanged.
- Agent-visible prose uses one paragraph per line. `instruction.md` retains the objective, inputs, interfaces, necessary limits and correctness criteria. API client details are in `environment/docs/available_resources.md`; judge repetitions and aggregation are author-facing details in this README/validation record, `raw-instruction.md` and grading code. The source-to-request review intentionally omits these evaluator internals from the agent instruction, while preserving the implementation contract and linking the API resource policy.
- Environment docs describe the CPU image, Java 21 runtime, Node/npm and installed packages. The resource doc preserves the task-specific Jina/OpenRouter clients and limits while removing generic credential tutorials. There are no GPU model/VRAM descriptions to remove and neither Compose overlay has a workspace tmpfs to change.
- Public validation is restored as `data/validation/queries.jsonl`, `ground_truth.jsonl` and `evidence.jsonl`. All three preserve their original bytes and five rows. The obsolete bundled copies and the local old-name answer duplicate were removed only after a clean remote download passed size/SHA-256 verification. Hidden input bytes are unchanged.

## Asset publication

The public files were published through [HF PR 9](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/9), merged as `102f2baf7980f81220d8c5519ff97b3edd369e21`. The task manifest pins that merged commit for the three public files and retains the existing history pin `d931a7d5645d84f54ee33258b63f7eaae528479f`. All 52,406 previous official manifest records were preserved. The upload included the public examples and source/license notices, with no hidden examples. Remote staged files were compared byte for byte before merging.

Publication records and clean-download evidence are retained locally at `../task_development/icsi-meeting-memory-review-20261104/` relative to the repository root. The staging helper was applied to the three selected new public assets; the already-published history was neither reuploaded nor repinned.

## Checks executed

| Check | Result |
| --- | --- |
| Build agent image from `environment/Dockerfile` | Passed; `search-swe-local:bingyu-icsi-agent-20261104` |
| Build verifier image from `tests/Dockerfile` | Passed; `search-swe-local:bingyu-icsi-verifier-20261104` |
| Task-local unittest discovery inside a disposable verifier container, network disabled, `TASK_ISOLATION_TEST=1` | 82 tests passed, no skips |
| Fixed-output judge averaging, failed judge handling, fractional joint/marginal scores and finalizer | Passed with mocked external API responses |
| Real build/search/answer subprocesses and submission/audit permission isolation | Passed in the disposable container |
| Fresh output directory and fresh HF cache using `scripts/assets/download_assets.py --task icsi-meeting-memory --output-dir .../fresh-download --cache-dir .../fresh-download-cache` | All four files downloaded; size/SHA-256 checks passed |
| `python3 scripts/assets/download_assets.py --task icsi-meeting-memory --verify-only` | Four files verified; zero failures |
| `python3 scripts/validation/check_release.py` | Zero errors and warnings |
| `python3 scripts/validation/check_tasks.py --merge-ready --base 783d2eeafd580f64c404da94dfc05733811d5c0f tasks/icsi-meeting-memory` | Zero errors |
| Both Compose overlays merged with a temporary base service; `bash -n tests/test.sh` | Passed |
| Agent-visible paragraph formatting and three judge-variable mappings | Passed |

The container test command mounted the current task at `/task-package:ro`, current tests at `/tests:ro`, history at `/task/data/history.jsonl:ro`, selected `/task-package/tests` as the working directory, and ran `python -B -m unittest discover -v -p 'test_*.py'` with 8 CPUs and 8 GiB RAM. No real provider credentials or model requests were used in these tests.

## Final revision and remaining evaluation

Final instruction SHA-256: `80f8b6547c2753534c3801a96f0a062001276b3443e6ca8ef10e27504672144c`. Grading harness SHA-256: `56e7247be4aee1e1e6b1d8f3ff9db27c10eac327ed9782d2a13976e6be306fab`.

No fresh coding-model trial or live 143-question judge evaluation has been run for this revision. The regression suite validates implementation and isolation, not model quality, real-service reliability or final API latency. There is no new empirical score or trajectory for this revision, and the historical normalization anchor has not been recalibrated. A full model rerun remains the next evaluation layer before claiming release readiness. No GitHub commit, push or PR was made for these local changes.
