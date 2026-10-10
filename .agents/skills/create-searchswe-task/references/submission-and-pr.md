# Contribution branch and PR handoff

Choose a descriptive task name of at most five lowercase hyphen-separated words,
starting with a letter and otherwise using letters/digits. Omit `task-`; `all`
is reserved. Choose GPU only when execution requires it.

## Local work first

Resolve the target checkout explicitly and inspect status, branch, remotes and
base. Preserve other authors' work and commits; never reset, stash or switch
their branch to simplify your task. Agree on branch/commit scope before changing
history. New packages use `tasks/<task-name>` in the contribution branch, with
`task.name = "search-swe/<task-name>"`. Check names against the current base and
active PRs. A PR may add multiple uniquely named tasks. Complete the scaffold's
instructions, assets, environment and grader before runtime validation.

Set actual `task.toml` authors. Preserve original commits and account-linked Git
name/email; do not change identity configuration on their behalf. Co-authored-by
trailers supplement these records.

In an approved clean checkout, a local branch could use
`git switch -c add-example-search`. Inspect the base and branch name first.
Local work permission does not itself authorize commits, forks, pushes, dataset
publication, PR creation/comments or remote configuration; reuse any explicit
session authorization already supplied.

## Authorized GitHub handoff

If remote access is authorized, preflight `gh --version` and
`gh auth status --hostname github.com` without recording tokens or auth output.
If missing/unavailable, stop the remote step and provide a local handoff; never
run login/configuration changes implicitly. Identify the exact upstream
`OWNER/REPO`, base branch, fork owner and contribution branch from real metadata.
Do not infer the repo from the installed skill's location.

Only after explicit commit/push/PR authorization, review the diff and selectively
stage the task and necessary integration files. Never use blanket staging in a
dirty checkout. Preserve real commit authors. Example handoff commands (replace
all uppercase values with verified values):

```bash
git push FORK_REMOTE CONTRIBUTION_BRANCH
gh pr create --repo OWNER/REPO --base BASE_BRANCH \
  --head FORK_OWNER:CONTRIBUTION_BRANCH --title 'Add example-search task' \
  --body-file /path/to/reviewed-pr-body.md
```

Use a trusted body file, not shell interpolation of task/PR text. Report actual
validation commands/results and unrun layers. For each task, name the reviewed
reference packages consulted (or state that none was close), the structural
patterns reused, and intentional differences; do not claim precedent as proof
that a task-specific value is correct. Link any authorized personal HF repo at
its immutable SHA. Do not call a static pass E2E success. After opening,
the **PR author** enables **Allow edits from maintainers** on the PR. Verify the
setting (`maintainerCanModify` in `gh pr view --json maintainerCanModify`), rather
than assuming PR creation enabled it. Same-repository branches may not need it;
organization-owned forks/policies may make it unavailable. In that case agree
that the contributor applies review fixes in the same PR. Never
request broad credentials or silently replace the PR.

## Review and finalization in the same PR

The maintainer audits instructions/resources, heldout split, known-good and
negative cases, model-trial feedback, grader isolation, networking/credentials,
sources and licenses. Separately authorize code execution, API/GPU costs and
credentialed runtime tests. Track each required check for the reviewed head.

Refresh the base and check names against queued PRs. Apply review fixes and
necessary inventory or documentation changes in the contribution branch,
preserving original author commits. Follow [publication](publication.md):
publish approved dataset inputs under official `tasks/<task-name>/...` paths,
merge the HF change, then pin its official SHA in `assets.json` and verify clean
downloads. Preserve original model pins.

Run release checks, applicable tests and `python scripts/check_tasks.py
--merge-ready --base FULL_PR_BASE_SHA`. Commit the reviewed changes in the same
PR. Re-review each changed head and verify required checks against the current
base before an authorized **merge commit**.

Verify the resulting SHA/tree and attribution using
`git log --follow -- tasks/example-search/instruction.md` and `git blame`.
Report observed outcomes, task names, official asset SHAs and remaining blockers.
