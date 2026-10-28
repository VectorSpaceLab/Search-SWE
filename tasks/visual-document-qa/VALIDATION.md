# Validation

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
python scripts/check_tasks.py tasks/visual-document-qa
python scripts/check_release.py
python scripts/check_tasks.py --merge-ready --base bb0ddbaf105c25cc53e3598c37e0428c943a7098
git diff --check
```

The task static check reported zero errors; the release check reported zero
errors and zero warnings. Merge-ready and whitespace checks also passed.

Re-evaluation of the four existing model submissions is pending maintainer
merge and pull. No coding-agent rerun is required for this correction. No
submission was re-evaluated and no live judge API was called in this change.
