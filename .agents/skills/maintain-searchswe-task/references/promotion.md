# Same-PR promotion and closed-loop merge

## Preserve the task name and authors

Complete the audit and resolve allowed branch editing first. A PR may contain
multiple uniquely named tasks under `task-submissions/<task-name>`. Names use at
most five lowercase hyphen-separated words, start with a letter, omit `task-`
and cannot be `all`. Keep all tasks in the same PR. Refresh the upstream base
and head, inspect formal task names and queued PRs for collisions, and update
against the base without flattening contributor history. A changed base/head
requires renewed review and validation.

Use a clean disposable checkout at the reviewed head. Set `REPO` to that checkout
and `SKILL_DIR` to this installed folder. Helpers require Python 3.12+, Git and
explicit `--repo-root`; they have no target Python imports or sibling-skill
dependency. They never commit, push or publish. Promotion keeps the task name:

```bash
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  rename task-submissions/example-search example-search --dry-run
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  rename task-submissions/example-search example-search
git -C "$REPO" diff --cached --summary
```

Repeat independently for each task; a rename commit contains exactly one whole
package move. Rename performs only `git mv` and refuses dirty worktrees,
collisions, traversal, symlinks and a target name different from the submission.
Review all staged files as R100 identical, with no incidental edits. The operator
creates the separately authorized pure rename commit. Preserve original author
commits and use real maintainer identity for maintainer changes.

```bash
# After the operator creates that separate pure-rename HEAD commit:
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  finalize task-submissions/example-search example-search --dry-run
python "$SKILL_DIR/scripts/promote_task.py" --repo-root "$REPO" \
  finalize task-submissions/example-search example-search
```

Finalize requires a single-parent, whole-package, pure rename HEAD commit.
It changes submission paths in tracked text only, preserving the task name and
canonical identity. It refuses unsupported binary rewrites. Review replacements,
relative mounts, image/URL paths and authors. Update task lists, docs and GPU
test inventories as needed. It does not edit downloaded data or assign licenses.
Resolve collisions before promotion; never overwrite another task or flatten
history. Keep all finalization edits separate from the pure rename commit.

## Assets and finalization commit

Read [publication.md](publication.md). Prepare only the new official files under
`tasks/<task-name>/...` using the bundled HF helper; preserve existing manifest entries,
model pins, provenance/license metadata. Its hash checks are offline and do not
prove remote freshness or grant upload permission. Official publication and HF
PR merge each require authorization. Merge official HF changes **first**, then
pin the resulting official 40-hex commit in GitHub `assets.json`, not community
PR SHA or mutable `main`. Verify clean downloads at that pin.

Run the audited target tools and relevant runtime layers, with approvals:
`check_release.py`, `check_submission.py --merge-ready`, full scripts/tests,
scaffold regression tests if changed, task-specific cases and `git diff --check`.
HF migration is per task. Confirm no submission `task.toml` or submission-path
references remain for any task. Review and let the authorized operator create
each needed finalization commit in **the same PR**; no empty commit is required. Helpers do not commit. Before an authorized push, verify remote head still
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

After explicit merge authorization and fresh head/base/name checks:

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
3. Inspect the merged tree for `tasks/<task-name>/task.toml`, actual authors, final
   official pins, no submission package/submission-path references and intended files.
   Compare it with the reviewed final tree (account for reviewed base integration).
4. Check `git log --follow -- tasks/<task-name>/instruction.md` and
   `git blame tasks/<task-name>/instruction.md` at the merge SHA. Original unmodified
   lines should retain contributor attribution. GitHub's latest file author and
   contributor statistics are not substitutes; stats also depend on linked email.
5. Report repo/PR, reviewed head/base, merge SHA, final path, official HF SHA,
   check/runtime evidence and author/history outcome. Do not retire personal
   development assets until verified official downloads work.
