# Validation

## 2026-10-28 grading correction

Base revision: `bb0ddbaf105c25cc53e3598c37e0428c943a7098`.

The 2026-10-28 correction adds 18 reviewed alternative passages across nine
reports: 26 label locations for 18 held-out questions. Corpus slices at each
new location match the corresponding reference row exactly. Table context was
reviewed for entity, financial item, period, unit and column meaning. All
existing evidence units and locations are retained.

The regression cases exercise the repeated net-income row, two debt facts in
the report summary, duplicate alternatives and incomplete/wrong-report spans.
The corpus, public examples, question split, instruction, task version and
score mapping are unchanged.

From the repository root, with Python 3.12:

```bash
unshare -n python -m unittest discover -s tasks/financial-report-qa/tests -p 'test_*.py'
```

Result: 35 tests passed.

Additional checks passed:

```bash
python scripts/check_tasks.py tasks/financial-report-qa
python scripts/check_release.py
python scripts/check_tasks.py --merge-ready --base bb0ddbaf105c25cc53e3598c37e0428c943a7098
git diff --check
```

The task static check reported zero errors; the release check reported zero
errors and zero warnings. Merge-ready and whitespace checks also passed.

Re-evaluation of the four existing model submissions is pending maintainer
merge and pull. No coding-agent rerun is required for this correction. No
submission was re-evaluated and no live judge API was called in this change.
