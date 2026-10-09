# Task submissions: review buffer, not a task registry

Create new tasks at
`task-submissions/<first-name-slug>/<category>-x-<positive-ordinal>`, with an
exactly matching internal canonical ID such as `task-1-x-1` or `task-2-x-1`.
Use a contributor-supplied first name, **not a username**: `Alice` → `alice`,
`Mary Jane` → `mary-jane`. For a
non-Latin name, supply your preferred ASCII transliteration. Slugs match
`[a-z][a-z0-9]*(?:-[a-z0-9]+)*`.

A PR may add multiple tasks, but all use exactly one contributor namespace.
Reuse that directory and choose temporary positive ordinals unique within each
category in the PR/checkout; ordinals are not final IDs. Do not reuse an ordinal
after its task is promoted in that PR. Check active PRs for a different person
with the same first name; that contributor explicitly chooses
`alice-2`, then `alice-3`. The scaffolder reuses existing namespaces and does
not derive name suffixes from task collisions. A name is not identity
authentication or permanent credit; use real `task.toml` authors and correct
Git author metadata.

```bash
python .agents/skills/create-searchswe-task/scripts/scaffold_task.py task-1-x-1 \
  --submission-first-name Alice --author 'Alice Example' \
  --mode implementation --hardware cpu
python scripts/check_submission.py task-submissions/alice/1-x-1
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1 --dry-run
python scripts/run_task.py --task-path task-submissions/alice/1-x-1 \
  --agent pi --model deepseek/deepseek-flash --dry-run
```

A scaffold intentionally fails verification until implemented. `--task all`
only discovers formal `tasks/*/task.toml` packages; submissions need explicit
`--task-path`. Read the [complete contribution guide](../docs/contributing.md).
No submission is merged unfinished. A maintainer performs a separate pure
rename and finalization for every task in that same PR; all must be promoted
before a **merge commit**. Official asset migration is per task.
This README stays on main; submission task packages do not.
