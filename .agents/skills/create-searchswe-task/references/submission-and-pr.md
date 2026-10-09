# Submission, branch and PR handoff

Choose `task-1-x-<positive-ordinal>` with `--mode implementation`
(`metadata.task_type = "create"`) or `task-2-x-<positive-ordinal>` with
`--mode optimization` (`"optimize"`). Hardware is independent. The canonical
ID exactly matches the temporary directory with the `task-` prefix.

## Local work first

Resolve the target checkout explicitly and inspect `git status --short`, current
branch, remotes and base before editing. Preserve dirty work and other authors'
commits; never reset, stash or switch their branch to make your task easier.
Agree on local branch/commit scope before changing history. New submissions use
`task-submissions/<first-name-slug>/<1|2>-x-<positive-ordinal>`, with exactly
matching canonical IDs such as `task-1-x-1`/`task-2-x-1`, not usernames or
guessed formal numbers. A scaffold is a deliberately failing starting point,
not a finished task. One PR may add multiple tasks, but all must use exactly one
contributor namespace; ordinals are temporary, category-local, and unique in
that PR/checkout, not final IDs. Do not reuse a temporary path after promoting
its earlier task in the same PR; the base-history CI check rejects reuse and
new formal tasks with no submission history.

Set `task.toml` authors to the actual author(s). Keep the contributor's original
commits and Git name/email (account-linked or GitHub noreply); do not change
identity configuration on their behalf. Co-authored-by trailers can supplement
this, not replace actual authors or original commits. An ASCII first-name slug
is only a temporary namespace and is reused for all tasks in that PR. Check
authorized read-only PR listings for another contributor with the same first
name and explicitly choose `alice-2`, `alice-3`, etc. if needed; the scaffolder
does not generate those suffixes from task collisions.

In an approved clean checkout, a local branch could be created with
`git switch -c add-alice-implementation`. Inspect the selected base and branch
name first; do not reuse an existing branch blindly. Local work permission does
not imply permission to commit, fork, push, publish datasets/images, open a PR,
post comments/reviews, change credentials or repository configuration.

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

Near merge, the maintainer serially assigns each task's next free category
number from the current base and queued PRs. The contributor must not guess or
reserve final numbers.
Update the PR to the current base without flattening the author's history.
Using the target checkout's offline `scripts/promote_task.py` (missing tools
are a prerequisite blocker), from a clean worktree/index:

```bash
# FINAL_ID is assigned by the maintainer, never inferred from this example.
python scripts/promote_task.py rename task-submissions/alice/1-x-1 FINAL_ID --dry-run
python scripts/promote_task.py rename task-submissions/alice/1-x-1 FINAL_ID
# Review and, only when authorized, commit this pure git mv alone.
python scripts/promote_task.py finalize task-submissions/alice/1-x-1 FINAL_ID --dry-run
python scripts/promote_task.py finalize task-submissions/alice/1-x-1 FINAL_ID
```

Repeat this pair of commands and separate commits independently for every task.
Finalize requires HEAD to be that task's separate, 100%-identical pure rename
commit of the whole package. Helpers never commit or publish. Review all replacements, image
and external paths, task inventories and authors. Complete the bundled
[publication workflow](publication.md): personal pinned development assets →
new official final-ID paths via HF community PR or authorized maintainer mirror
→ official merge → pin official SHA (not the community PR SHA). Preserve model
pins. Then validate every final package with release checks, full applicable tests
and `python scripts/check_submission.py --merge-ready`; no submission task.toml
may remain. HF migration is per task. Commit each finalization separately in
**the same PR** when authorized.

Maintainers re-review each head change, recheck the base/ID and exact head before
an authorized **merge commit**; no squash/rebase, admin bypass or unfinished
submission on main. Keep original author commits. Verify the resulting merged
SHA/tree and `git log --follow -- tasks/FINAL_ID/instruction.md` and
`git blame tasks/FINAL_ID/instruction.md` for history/attribution. Report the PR,
final ID, official asset SHA, checks and any outstanding blockers rather than
claiming a merge that was not observed.
