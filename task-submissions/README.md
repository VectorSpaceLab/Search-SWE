# Task submissions

Create new tasks at `task-submissions/<task-name>`, with `[task].name` set to
`search-swe/<task-name>`. Use at most five lowercase, hyphen-separated words,
starting with a letter, such as `example-search`. The `task-` prefix and `all`
are reserved. Names must be unique across submissions and
formal tasks; check active PRs for conflicting names before handoff.

One PR may add multiple tasks. Use actual `task.toml` authors and correct Git
author metadata.

```bash
python .agents/skills/create-searchswe-task/scripts/scaffold_task.py example-search \
  --author 'Alice Example' --hardware cpu
python scripts/check_submission.py task-submissions/example-search
python scripts/download_assets.py --task-path task-submissions/example-search --dry-run
python scripts/run_task.py --task-path task-submissions/example-search \
  --agent pi --model deepseek/deepseek-flash --dry-run
```

A scaffold intentionally fails verification until implemented. Automatic task
discovery only includes formal `tasks/*/task.toml` packages; submissions need
explicit `--task-path`. See the [complete contribution guide](../docs/contributing.md).

Before promotion, run a configured coding-model trial alongside grader checks.
Use the trajectory and scores to refine the task setting where needed, revalidate
substantive changes, and report the final tested revision and any missing evidence.
The authoring skill explains how to request local configuration of missing API keys.

Promote every package to `tasks/<task-name>` in the same PR, preserving its
name. Each pure move is committed separately from finalization; preserve the
contributor's commits with a merge commit. Do not reuse a submission path in
the same PR after removing or promoting it. No submission package enters main;
this README stays as the workflow entry point.
