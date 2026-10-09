# Same-PR promotion and closed-loop merge

## Assign and rename, preserving authors

Complete the audit and resolve allowed branch editing first. A PR may contain
multiple tasks only under exactly one contributor first-name namespace. Keep all
of them in the same PR throughout. Near merge, refresh the exact upstream
base/head and serialize each ID assignment with other queued PRs: inspect
`tasks/` on the current base, choose the next free positive number in the same
category, and recheck immediately before merge. Temporary category-local
ordinals are not final IDs. Never infer a number from examples or reserve it
long-term. Update
against the current base without rebasing away original contributor commits.
If base/head moves, re-review/revalidate affected work; a collision blocks merge.

Use a clean disposable worktree and index at the reviewed PR head. Set `REPO` to
that checkout (not the user's dirty checkout), `SKILL_DIR` to this installed
folder, and `FINAL_ID` to the actually assigned ID. Bundled helpers require
Python 3.12+, Git for promotion, and explicit `--repo-root`; no target Python
imports or sibling skill. They never commit, push, publish or allocate an ID.

```bash
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  rename task-submissions/alice/1-x-1 "$FINAL_ID" --dry-run
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  rename task-submissions/alice/1-x-1 "$FINAL_ID"
git -C "$REPO" diff --cached --summary
```

Repeat rename and finalize independently for every task, using separate commits;
a rename for one task must not include another. Rename performs **only `git mv`**
and refuses dirty worktrees, collisions, traversal, symlinks and category
mismatches. Review the staged diff: every package
file must be R100 identical, with no incidental changes. Stop for the operator's
explicitly authorized separate pure-rename commit; never auto-commit. Retain the
contributor's existing commits/authors; use the maintainer's real identity for
maintainer changes, not forged author flags or global identity changes.

```bash
# Only after the operator creates that separate pure-rename HEAD commit:
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  finalize task-submissions/alice/1-x-1 "$FINAL_ID" --dry-run
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  finalize task-submissions/alice/1-x-1 "$FINAL_ID"
```

Finalize requires the entire package to have moved in a single-parent pure-rename
HEAD commit. It changes temporary IDs/submission paths in tracked text only;
it refuses nonstandard binary/filename rewrites. Review all replacements,
relative mounts, image/URL paths and author fields manually. Update task lists,
docs and explicit GPU test inventories only as needed. It does not edit downloaded
data or assign source licenses. Collision/unsupported reference means stop and
coordinate another reviewed rename/finalization, not overwrite or flatten history.

## Assets and finalization commit

Read [publication.md](publication.md). Prepare only the new official files under
`tasks/<final-id>/...` using the bundled HF helper; preserve old manifest entries,
model pins, provenance/license metadata. Its hash checks are offline and do not
prove remote freshness or grant upload permission. Official publication and HF
PR merge each require authorization. Merge official HF changes **first**, then
pin the resulting official 40-hex commit in GitHub `assets.json`, not community
PR SHA or mutable `main`. Verify clean downloads at that pin.

Run the audited target tools and relevant runtime layers, with approvals:
`check_release.py`, `check_submission.py --merge-ready`, full scripts/tests,
scaffold regression tests if changed, task-specific cases and `git diff --check`.
HF migration is per task. Confirm no submission `task.toml` or temporary
references remain for any task. Review and let the authorized operator create
each separate finalization commit in **the same PR**. Helpers do not commit. Before an authorized push, verify remote head still
matches the reviewed starting head, branch/permissions and intended commits;
use a normal push, not force. Any new head requires fresh review/check evidence.

## Review, merge and verify

Prepare a review summary locally by default. Only post a comment/review after
explicit authorization for its content, repo and PR. Example commands (replace
verified values and use a trusted body file):

```bash
gh pr comment PR --repo OWNER/REPO --body-file /path/to/reviewed-comment.md
gh pr review PR --repo OWNER/REPO --request-changes --body-file /path/to/review.md
# Or --approve only when the head is actually accepted and posting is authorized.
```

Re-query the full head/base immediately before posting or merging; new commits
invalidate prior approval. The gh review command has no match-head flag: bind
review evidence to its full SHA, check again after posting, and resolve any race
rather than claiming acceptance of the changed head. All required human reviews,
resolved conversations, `review-stage`, `merge-ready` and other configured checks
must pass for that exact head and current base. Missing/pending checks block.
If protections/merge queue prevent the specified method, stop, do not bypass.

After explicit merge authorization and fresh head/base/ID checks:

```bash
gh pr merge PR --repo OWNER/REPO --merge --match-head-commit FULL_REVIEWED_HEAD_SHA
```

**Merge commit only**: no `--squash`, `--rebase`, `--admin`, auto-merge shortcuts
or branch deletion unless separately requested. No unfinished submission reaches
main. `--match-head-commit` guards the head, not a concurrent base change: serial
coordination/current-base policy is still required. Never silently configure
protections, a queue or CODEOWNERS identities.

Close the loop after the command, rather than treating exit zero as proof:

1. Query `gh pr view PR --repo OWNER/REPO --json state,mergedAt,mergeCommit,headRefOid,baseRefName`.
   Confirm MERGED and record the full merge SHA; if queued/not merged, report that.
2. Fetch the resulting base/merge into the disposable checkout. Verify the merge
   object has two parents, the accepted PR head is its second parent, the reviewed
   base is its first parent, and original author commits are ancestors. Unexpected
   parent/base/tree changes require investigation, not a success claim.
3. Inspect the merged tree for `tasks/<final-id>/task.toml`, actual authors, final
   official pins, no submission package/temporary references and intended files.
   Compare it with the reviewed final tree (account for reviewed base integration).
4. Check `git log --follow -- tasks/<final-id>/instruction.md` and
   `git blame tasks/<final-id>/instruction.md` at the merge SHA. Original unmodified
   lines should retain contributor attribution. GitHub's latest file author and
   contributor statistics are not substitutes; stats also depend on linked email.
5. Report repo/PR, reviewed head/base, merge SHA, final path, official HF SHA,
   check/runtime evidence and author/history outcome. Do not retire personal
   development assets until verified official downloads work.
