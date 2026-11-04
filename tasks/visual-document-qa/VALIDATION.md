# Validation

## 2026-11-04 recoverable answer judging

This revision supersedes the earlier three-attempt terminal failure and 300-second wait rejection described in the historical sections below. Temporary transport/service failures now defer unfinished questions after three local attempts and resume within the existing time budget. A shared cooldown honors `Retry-After` without discarding a run merely because the requested delay exceeds five minutes. Credential/configuration errors stop promptly. Pending requests are bounded by the concurrency setting and cancelled on terminal failure.

Successful samples are atomically written, flushed and checksummed in protected verifier logs. Frozen validated answers can be resumed with `/opt/conda/bin/python /tests/grader.py --resume-judging`; build and answer generation are skipped. Model, judge source/prompts, evaluation inputs and answer identities bind checkpoint reuse. Failed or incomplete samples never enter the score, and all three successful samples, including zeros, must be present before averaging. Initial invalid status replaces stale success before execution begins.

All 79 offline tests passed in the disconnected disposable container described below. Added coverage includes three consecutive connection failures followed by recovery, deferred work without duplicate saved samples, abrupt child-process exit and checkpoint reuse, interrupted atomic replacement, zero-score retention, corrupt/changed checkpoints, deadline/cancellation behavior, fail-fast authentication, and a resume through the main grading entry point without executing a submission again. Static task validation and the whitespace check passed. Submission execution and scoring rules, model/prompt settings, default concurrency 32, task version `1.0.0`, README Change Log and the independent trajectory judge remain unchanged.

No paid API inference, live network-fault test or complete model trial was run. Recovery requires retained protected trial logs; it cannot recover deleted storage. A resumed answer-judge invocation updates its evaluation report only; the original trial's trajectory audit and reward finalization remain separate required steps. Persistent infrastructure failure still leaves an invalid/incomplete measurement, not a score over a reduced question set.

## 2026-11-04 judge concurrency increase

The answer-judge concurrency default increased from 8 to 32. `JUDGE_MAX_CONCURRENCY` is a positive-integer verifier setting; it does not enter the submission environment. Each question retains three sequential judgments, so there are at most 32 in-flight calls by default, not 96. The verifier records `judge_max_concurrency` and `judge_seconds`.

The three-attempt request limit is retained. Retries now use 2/4-second exponential backoff plus 0–1 seconds of jitter and honor numeric or HTTP-date `Retry-After` headers on HTTP 402/429/503 responses. A requested wait over 300 seconds invalidates the measurement rather than retrying ahead of the server's requested time. See the [OpenRouter error documentation](https://openrouter.ai/docs/api_reference/errors-and-debugging#retry-after-header) for the header contract.

All 61 offline tests passed using the disconnected disposable-container command below. Added checks exercise real thread pools at concurrency 4 and 32, preserve every result and input ordering, propagate worker failures and verify transient/persistent rate limits, malformed retry headers and bounded waiting. Task static validation reported zero errors and the whitespace check passed. Task version `1.0.0`, historical Change Log, judge model/prompts, three-sample averaging and scoring rules are unchanged. No paid model call or live throughput/error-rate measurement was made; shorter runtime and fewer failures have not been established empirically.

## 2026-11-04 answer judge replacement

On branch `fix/task-agent-facing-content`, based on `c7f8a8064e0ff1be30bca3bf4b42ab6b18e60b03` with the existing local review fixes retained, the answer judge now uses `deepseek/deepseek-v4.1-flash-1017`. The public [OpenRouter catalog](https://openrouter.ai/api/v1/models) confirms this exact ID, optional reasoning and structured-output parameters; its [provider listing](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash-1017/endpoints) includes compatible endpoints. These were read without credentials or inference calls.

Requests disable reasoning, cap output at 512 tokens and require providers to support all requested parameters. The FinRAG JSON schema now uses `analysis`, matching its unchanged prompt. Truncated responses are retried and cannot become accepted extracted answers or judgments. Three judgments per answer, numeric comparators, source aggregation, score mapping, the trajectory judge, task version `1.0.0` and the historical README Change Log are retained.

All 52 offline tests passed in a disposable container with networking disabled and the task mounted read-only. Coverage includes default/override model selection, request parameters, JSON contracts, malformed/truncated responses, bounded retries, grading routes and three-sample aggregation. The task static check reported zero errors; `git diff --check` passed. From the repository root, the checks were:

```bash
docker run --rm --network none --cpus 1 --memory 1g --pids-limit 128 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/tasks/visual-document-qa:/package:ro" \
  --entrypoint /opt/conda/bin/python \
  scientific-paper-qa__kakd4ez__verifier__trial-main:latest \
  -m unittest discover -s /package/tests -p 'test_*.py' -v
python scripts/validation/check_tasks.py tasks/visual-document-qa
git diff --check -- tasks/visual-document-qa
```

All inference responses were mocked. Live model accuracy, output-budget adequacy, latency, interruption frequency and full-evaluation completion remain unmeasured. Existing scores and the baseline anchor have not been recalibrated for this judge configuration; the model replacement alone does not resolve missing checkpoint recovery or provider failures.

## 2026-10-28 grading correction

Base revision: `bb0ddbaf105c25cc53e3598c37e0428c943a7098`.

The 2026-10-28 correction sends MMLongBench-Doc Str/List/None answers directly
to the semantic judge. Tests check full-answer forwarding, structured binary
responses, malformed responses, retries and failure propagation. Numeric
extraction/comparison and the FinRAGBench-V judge retain their existing routes.
All API responses in these tests are mocked; network access is disabled.

The instruction, task version, reference answers and score mapping are
unchanged. These tests check verifier behavior; they do not measure the
accuracy of a live semantic judge.

From the repository root, with Python 3.12:

```bash
unshare -n python -m unittest discover -s tasks/visual-document-qa/tests -p 'test_*.py'
```

Result: 45 tests passed.

Additional checks passed:

```bash
python scripts/validation/check_tasks.py tasks/visual-document-qa
python scripts/validation/check_release.py
python scripts/validation/check_tasks.py --merge-ready --base bb0ddbaf105c25cc53e3598c37e0428c943a7098
git diff --check
```

The task static check reported zero errors; the release check reported zero
errors and zero warnings. Merge-ready and whitespace checks also passed.

Re-evaluation of the four existing model submissions is pending maintainer
merge and pull. No coding-agent rerun is required for this correction. No
submission was re-evaluated and no live judge API was called in this change.
