# Submission, branch and PR handoff

Choose a descriptive task name of at most five lowercase hyphen-separated words,
starting with a letter and otherwise using letters/digits. Omit `task-`; `all`
is reserved. Choose GPU only when execution requires it.

## Local work first

Resolve the target checkout explicitly and inspect status, branch, remotes and
base. Preserve other authors' work and commits; never reset, stash or switch
their branch to simplify your task. Agree on branch/commit scope before changing
history. New packages use `task-submissions/<task-name>` and canonical
`task.name = "search-swe/<task-name>"`. Check formal tasks, submissions and active
PRs for collisions. A PR may add multiple unique names, but cannot reuse a
submission path. Direct new formal additions without submission history fail CI.
A scaffold is a deliberately failing starting point, not a finished task.

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
  --head FORK_OWNER:CONTRIBUTION_BRANCH --title 'Add task submission' \
  --body-file /path/to/reviewed-pr-body.md
```

Use a trusted body file, not shell interpolation of task/PR text. Report actual
validation commands/results and unrun layers. For each task, name the formal
reference packages consulted (or state that none was close), the structural
patterns reused, and intentional differences; do not claim precedent as proof
that a task-specific value is correct. Link any authorized personal HF repo at
its immutable SHA. Do not call a static pass E2E success. After opening,
the **PR author** enables **Allow edits from maintainers** on the PR. Verify the
setting (`maintainerCanModify` in `gh pr view --json maintainerCanModify`), rather
than assuming PR creation enabled it. Same-repository branches may not need it;
organization-owned forks/policies may make it unavailable. In that case agree
that the contributor performs the promotion commits in the same PR. Never
request broad credentials or silently replace the PR.

## Review and finalization in that same PR

The maintainer audits instructions/resources, heldout split, known-good and
negative cases, grader isolation, networking/credentials, sources and licenses.
A review-stage CI pass can still contain unfinished submissions. Missing,
pending or failed checks are not acceptance. Separately authorize code execution,
API/GPU costs and any credentialed runtime tests.

Near merge, refresh the base and check name collisions with queued PRs. Preserve
original author history. Use the target checkout's offline promotion helper
from a clean worktree/index; missing tools are a prerequisite blocker:

```bash
python scripts/promote_task.py rename task-submissions/example-search example-search --dry-run
python scripts/promote_task.py rename task-submissions/example-search example-search
# Review and, only when authorized, commit this pure git mv alone.
python scripts/promote_task.py finalize task-submissions/example-search example-search --dry-run
python scripts/promote_task.py finalize task-submissions/example-search example-search
```

Repeat independently for each task. The name stays unchanged. Finalize requires
HEAD to be that task's single-parent, whole-package, 100%-identical pure rename
commit. It rewrites submission paths in tracked text; it never commits or
publishes. Review replacements, mounts, image/external paths, inventories and
authors. Follow [publication](publication.md): personal pinned development data
→ official `tasks/<task-name>/...` paths through a community PR or authorized
mirror → official merge → pin that official SHA. Preserve original model pins.

Run release and applicable tests plus `python scripts/check_submission.py
--merge-ready`; no submission task.toml may remain. Commit any reference, asset
or integration finalization separately in this same PR. Do not create an empty
commit if no finalization changes are needed.

Re-review each changed head, recheck base/name collisions and exact head before
an authorized **merge commit**. No squash/rebase or unfinished submissions on
main. Verify the resulting SHA/tree and attribution using
`git log --follow -- tasks/example-search/instruction.md` and `git blame`.
Report observed outcomes, task names, official asset SHAs and remaining blockers.
