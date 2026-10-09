# Contributing to Search-SWE

Task packages, shared images, tools, tests, and documentation contributions are
welcome. Keep changes focused. For task authoring, read the
[create-searchswe-task skill](../.agents/skills/create-searchswe-task/SKILL.md)
(or invoke `$create-searchswe-task`) and the [agent workflow](../.agents/AGENTS.md).
Reuse the [shared CPU/GPU images](../docker/README.md). Keep the English and
Chinese README overviews aligned. Publication, remote configuration, and merges
require separate authorization; local task creation does not authorize them.

## 1. Start one or more tasks in one contributor namespace

Fork the repository, clone your fork, and create a task branch. From the
checkout root, use Python 3.12+ and install the host tools and static-test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r scripts/requirements.txt PyYAML python-dotenv
```

Do not guess or reserve final task numbers. Use:

```text
task-submissions/<first-name-slug>/1-x-1/   # internal ID: task-1-x-1
task-submissions/<first-name-slug>/1-x-2/   # second category 1 task
task-submissions/<first-name-slug>/2-x-1/   # internal ID: task-2-x-1
```

A PR may add multiple tasks, but all must use exactly one contributor first-name
namespace. The positive ordinal is temporary and unique within its category in
that PR/checkout; it is not the final task number. Do not delete a promoted
temporary path and reuse its ordinal later in the same PR. The canonical ID must
exactly match the directory with a `task-` prefix.

Supply your **first name, not your GitHub username**. ASCII lowercase slugs
match `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`; spaces/separators become `-`.
`Alice` becomes `alice`; a compound first name `Mary Jane` becomes `mary-jane`.
For non-Latin names, choose an ASCII transliteration. The scaffolder reuses the
same local contributor directory for additional task ordinals. Check active PRs
for a *different person* with the same first name: that contributor explicitly
passes `Alice-2`, then `Alice-3`; suffixes are not generated automatically from
task collisions. This is a temporary readable namespace, not proof of identity
or permanent attribution.

```bash
python .agents/skills/create-searchswe-task/scripts/scaffold_task.py task-1-x-1 \
  --submission-first-name Alice --author 'Alice Example' \
  --mode implementation --hardware cpu
```

Repeat `--author` for coauthors. `task.toml` must name actual task authors, not
only “Search-SWE”. Use a Git email associated with your GitHub account (or its
noreply address). Co-authored-by trailers supplement, not replace, authors and
original commits. The scaffold is deliberately incomplete and fail-closed.
Existing-task revisions stay in their formal directory. Regular scaffolding
without `--submission-first-name` remains available for maintainer/legacy use.

Do not commit credentials, downloaded inputs/models, hidden private evaluation
assets, job outputs, or author-only solutions. Keep tests isolated from the
agent, including any public repository test fixtures. Ignore runtime data and
models, and use an author-only copy for reference solutions.

## 2. Develop and validate before promotion

Development assets may live in a **personal public temporary HF dataset**, with
redistribution permission, manifest, provenance and license. Pin its immutable
40-character commit SHA in `assets.json`; arbitrary HF repos already work.
Do not publish temporary IDs as permanent official dataset paths or image tags.
See [asset contribution and publication](#asset-contribution-and-publication).

```bash
python scripts/check_submission.py task-submissions/alice/1-x-1
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python .agents/skills/create-searchswe-task/scripts/test_scaffold_task.py
git diff --check
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1 --dry-run
# After approving the download budget:
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1 --verify-only
python scripts/run_task.py --task-path task-submissions/alice/1-x-1 \
  --agent pi --model deepseek/deepseek-flash --dry-run
```

Both downloader and launcher require canonical repository-relative paths with
no traversal or symlinks. `--task all` remains formal-only (downloader); the
launcher still runs one selected task. Default submission outputs are under
`jobs/task-submissions/alice/1-x-1`, not a shared `jobs/1-x-1`. Alternate downloader
`--output-dir` also retains `task-submissions/alice/1-x-1`. The launcher uses the
original package's local assets, not an alternate download directory.

Follow the skill's [validation layers](../.agents/skills/create-searchswe-task/references/validation.md):
Compose rendering, builds, verifier known-good and negative cases, and an
end-to-end trial when authorized. Use a fresh `--output` for each trial. Static
checks alone do not prove solvability or safe grading. Record commands, actual
results, resource requirements, and unrun layers with reasons in the PR.
Enable **Allow edits from maintainers** so promotion stays in the same PR.
The PR author can enable this on the open PR after creation. For same-repository
branches it may be unnecessary; organization-owned forks or repository policies
can restrict availability. If unavailable, the contributor performs the same
promotion commits after the maintainer assigns the number.

### CI and trust boundaries

The unprivileged `pull_request` and `push` workflow checks formal packages and
**all** submission packages, including malformed/incomplete package paths.
For PRs it permits multiple newly added `task.toml` files but requires all
submission paths touched anywhere between the full base SHA and HEAD—including
packages already promoted and both sides of merge commits—to use exactly one
contributor namespace. It rejects reused temporary paths and newly added formal
tasks without submission history. The current submission tree is checked too.
The submission validator reuses release structure,
asset pin/hash, secret, file-size, and Git-ignore checks and parses Python,
shell, and Compose YAML without running task code. Install `PyYAML` for its
Compose syntax layer; full Docker Compose rendering remains a separate check.

`review-stage` may pass while submissions exist. **`merge-ready` must also pass
before merge**: `python scripts/check_submission.py --merge-ready` refuses any
remaining submission `task.toml` and repeats static checks on formal packages,
including syntax and temporary-reference checks. The PR base check also requires
actual authors on newly added formal packages; legacy author records are unchanged.
Every submission is promoted in this PR before merge; merge-ready passes only
after all temporary packages are gone. No GPU/API/container task execution occurs in CI. Never use
`pull_request_target` to run contributor code with secrets, share an official
HF token, or run an unreviewed task with maintainer credentials. Even repository
unit tests are PR-controlled code: CI has no secrets, read-only permissions,
and checkout does not persist credentials. Review and separately authorize
credentialed/runtime testing in a disposable trusted environment.

## 3. Maintainer promotion in the same PR

For self-contained gh review, trust gates, portable helpers and closed-loop merge
checks, use [maintain-searchswe-task](../.agents/skills/maintain-searchswe-task/SKILL.md).
The repository `scripts/promote_task.py` and `scripts/prepare_hf_upload.py` remain
compatible entrypoints; their implementation lives in that portable skill. When
copying only the skill, invoke its scripts with explicit `--repo-root /path/to/checkout`.

Finish design, provenance/license, environment, verifier-isolation and runtime
review first; explicitly approve any missing validation. Update the PR to the
latest main. Serialize each final ID assignment and merging (or use a separately
configured merge queue); inspect other queued PRs before selecting each next
free number in the same category. Temporary ordinals do not influence final
numbers. Do not reserve numbers long-term.

Start with a clean worktree/index. The helper never commits, pushes or publishes.
Example only: replace `task-1-6` with the actual free final ID.

```bash
python scripts/promote_task.py rename task-submissions/alice/1-x-1 task-1-6 --dry-run
python scripts/promote_task.py rename task-submissions/alice/1-x-1 task-1-6
git diff --cached --summary
# Operator creates the separate pure-rename commit:
git commit -m 'Promote submission as task-1-6'
python scripts/promote_task.py finalize task-submissions/alice/1-x-1 task-1-6 --dry-run
python scripts/promote_task.py finalize task-submissions/alice/1-x-1 task-1-6
```

Repeat the rename/finalize sequence independently for every task, with a
separate pure rename and finalization commit for each. Rename does **only
`git mv`**. Finalize requires HEAD to be the operator's single-parent,
100%-identical rename commit for that entire package. It updates
canonical temporary IDs and the old submission path only in tracked package
text files, prints changed lines, and refuses nonstandard/binary reference
rewrites. It does not edit downloaded data. Review all replacements, filenames,
image references, Compose paths and external URLs. Update repository task
lists/docs/test inventories (including explicit GPU inventories) manually.
Finalize is intentionally conservative, not a general re-numbering tool. If a
number becomes occupied, stop; coordinate a separately reviewed pure rename
and finalization to a new free ID without overwriting another task or flattening
history. Keep the PR up to date and recheck serially immediately before merging.

Finish official asset publication separately for each task, pin each merged
official SHA, then run full checks and applicable task-specific checks. Confirm
no temporary reference remains in any formal package and no submission
`task.toml` remains. Review and commit each finalization separately **in this
same PR**. Merge with a **merge commit
only**, not squash or rebase merge.

```bash
python scripts/check_release.py
python scripts/check_submission.py --merge-ready
python -m unittest discover -s scripts/tests -p 'test_*.py'
git diff --check
git log --follow -- tasks/task-1-6/instruction.md
git blame tasks/task-1-6/instruction.md
```

The original author commits and unmodified lines' blame survive this workflow.
GitHub's file list often shows the maintainer's latest change; History may not
follow renames as fully as `git log --follow`. Contributors statistics also
depend on account-linked email and reachability from the default branch.

Repository owners should separately configure required review, resolved review
conversations, current-base/queue checks, and required `review-stage` and
`merge-ready` statuses. Enforce merge-commit-only task PRs operationally if the
host cannot restrict merge methods by PR type. This change does **not** configure
remote protections, a merge queue, or CODEOWNERS identities. Maintainer review
is required regardless of automation. If branch editing is unavailable, resolve
that with the contributor before promotion; do not silently switch PRs or squash
away their commits.

## Asset contribution and publication

### Development: personal temporary dataset

Only upload redistributable public inputs, never private hidden answers or
secrets. Prepare a dataset folder containing `README.md` with license metadata,
`SOURCES.md`, `.gitattributes`, `manifest.json`, and new data. The dataset manifest
uses `{"schema_version": 1, "files": [{"path": "...", "size_bytes": 123,
"sha256": "..."}]}` with hashes of actual files. Document how each source was
obtained and its redistribution terms; do not invent a license.

The following are **operator-run publishing commands**, not part of local
validation. Authenticate with your own personal HF account/token using
`hf auth login`, after publication is authorized. Replace example paths/repos.

```bash
python - <<'PY'
from huggingface_hub import HfApi
api = HfApi()
repo = 'YOUR_ACCOUNT/search-swe-development'
api.create_repo(repo_id=repo, repo_type='dataset', private=False, exist_ok=True)
commit = api.upload_folder(repo_id=repo, repo_type='dataset', folder_path='/path/to/dev-data',
                           commit_message='Add temporary task development inputs')
print(commit.oid)  # Pin this full SHA in submission assets.json.
PY
```

Use this personal repo, its dataset-relative filenames, size/hash, and printed
immutable SHA in `assets.json`. The explicit submission downloader/launcher then
support real pre-promotion validation. Keep the temporary repo accessible through
review and migration; only retire it after official pinned downloads are verified.

### Final ID: additive official publication, then GitHub merge

After ID assignment/finalization, change only the new task's dataset source
repo/filename to `search-swe/Search-SWE` and `tasks/<final-id>/...`. Preserve
original model repo pins and bundled metadata. Prepare **only new data files**
in `/path/to/new-data/tasks/<final-id>/...`, at the exact asset sizes/hashes.
Do not delete, rename or overwrite existing official assets.

Fetch the small current official manifest snapshot and metadata, not the whole
dataset. Run this in a trusted publication workspace with your personal login:

```bash
python - <<'PY'
from pathlib import Path
import shutil
from huggingface_hub import HfApi, hf_hub_download
repo = 'search-swe/Search-SWE'
sha = HfApi().repo_info(repo_id=repo, repo_type='dataset').sha
out = Path('/path/to/official-snapshot'); out.mkdir(parents=True, exist_ok=True)
(out / 'BASE_SHA').write_text(sha)
for name in ('manifest.json', 'README.md', 'SOURCES.md', '.gitattributes'):
    shutil.copyfile(hf_hub_download(repo_id=repo, repo_type='dataset', revision=sha, filename=name), out / name)
print(sha)
PY
python scripts/prepare_hf_upload.py \
  --official-manifest /path/to/official-snapshot/manifest.json \
  --task-path tasks/task-1-6 --new-data /path/to/new-data \
  --output /path/to/upload-staging
```

This offline helper verifies new files' hashes, refuses collisions/traversal/
symlinks, and writes only new files plus a merged manifest preserving every old
record. It does not require old data or upload anything. A trusted current
snapshot is essential: it cannot prove remote freshness offline. Unlike
`check_release.py --hf-data`, which intentionally checks the **full inventory**,
this is the incremental contribution path, not a replacement full release audit.

Copy the snapshot `README.md`, `SOURCES.md`, and `.gitattributes` into staging,
then **append** provenance, license/redistribution information, and any required
LFS patterns for the new files without discarding existing entries. Update or
add applicable license files. Review this metadata and the generated manifest.
No delete patterns, sync deletion, or uploads of entire task code directories.

Submit a Hugging Face **community PR**, authenticated with your own account:

```bash
python - <<'PY'
from pathlib import Path
from huggingface_hub import HfApi
result = HfApi().upload_folder(
    repo_id='search-swe/Search-SWE', repo_type='dataset',
    folder_path='/path/to/upload-staging',
    parent_commit=Path('/path/to/official-snapshot/BASE_SHA').read_text().strip(),
    create_pr=True, commit_message='Add task-1-6 inputs and provenance',
)
print(result.pr_url)
PY
```

If community contributions are unavailable, ask a maintainer to mirror the
reviewed files from your personal public dataset using their own authorized
account. **Never request, grant or share the official dataset token.** Link the
HF PR and GitHub task PR. A maintainer must review merged-manifest preservation,
hashes, sources and licensing. If official HEAD changes, refresh the snapshot,
regenerate/review the merged manifest and coordinate the HF PR update; never
replace a newer manifest with a stale one.

**Merge the official HF change first.** Only then pin the resulting official
40-hex commit SHA (not the community PR/head SHA or `main`) in the finalized
GitHub task's `assets.json`. Verify downloads using a fresh output directory or
cache and run release checks. Commit finalization and merge the GitHub PR last.
No new task with unpublished/unpinned assets or an unfinished submission enters
main. Existing tasks' old pins and assets remain valid.
