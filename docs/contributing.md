# Contributing to Search-SWE

Task packages, shared images, tools, tests, and documentation contributions are
welcome. Keep changes focused. For task authoring, read the
[create-searchswe-task skill](../.agents/skills/create-searchswe-task/SKILL.md)
(or invoke `$create-searchswe-task`) and the [agent workflow](../.agents/AGENTS.md).
Reuse the [shared CPU/GPU images](../docker/README.md). Keep the English and
Chinese README overviews aligned. Publication, remote configuration, and merges
require separate authorization; local task creation does not authorize them.

## 1. Start tasks with descriptive names

Fork the repository, clone your fork, and create a task branch. From the checkout
root, use Python 3.12+ and install the host tools and static-test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r scripts/requirements.txt PyYAML python-dotenv
python .agents/skills/create-searchswe-task/scripts/scaffold_task.py example-search \
  --author 'Alice Example' --hardware cpu
```

New packages use `task-submissions/<task-name>/`. Choose a concise description
with at most five lowercase hyphen-separated words, starting with an ASCII
letter and otherwise using letters/digits. Omit the `task-` prefix; `all` is
reserved. Check both `tasks/` and `task-submissions/`, plus active PRs, for name
collisions. The canonical `task.name` is `search-swe/<task-name>` from the start,
and promotion preserves it. A PR may contain multiple uniquely named tasks;
do not reuse a submission path later in that PR.

Describe the task's goal, starting state and measured outcomes.
CPU is the default; choose `--hardware gpu` for actual GPU execution. Repeat
`--author` for coauthors. Use actual authors in `task.toml`, not only “Search-SWE”,
and a Git email associated with your GitHub account (or its noreply address).
Co-authored-by trailers supplement original commits and task authors.

The scaffold is deliberately incomplete and its verifier fails closed. Existing
task revisions stay in their formal directory. The explicit `--formal` scaffold
option supports maintainer tooling; new contributions still follow this workflow.
Do not commit credentials, downloaded inputs/models, private evaluation assets,
job outputs or author-only solutions. Keep verifier inputs isolated from agents.

## 2. Develop and validate before promotion

Development assets may live in a personal public temporary HF dataset with
redistribution permission, manifest, provenance and license. Pin its immutable
40-character commit SHA in `assets.json`. Official data will use
`tasks/<task-name>/...`; model files retain their original repository pins.
See [asset contribution and publication](#asset-contribution-and-publication).

```bash
python scripts/check_submission.py task-submissions/example-search
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python .agents/skills/create-searchswe-task/scripts/test_scaffold_task.py
git diff --check
python scripts/download_assets.py --task-path task-submissions/example-search --dry-run
# After approving the download budget:
python scripts/download_assets.py --task-path task-submissions/example-search
python scripts/download_assets.py --task-path task-submissions/example-search --verify-only
python scripts/run_task.py --task-path task-submissions/example-search \
  --agent pi --model deepseek/deepseek-flash --dry-run
```

Downloader and launcher require canonical repository-relative paths without
traversal or symlinks. `--task <task-name>` selects a formal package; downloader
`--task all` selects only formal packages. Submissions require `--task-path`.
Submission jobs default to `jobs/task-submissions/<task-name>` and alternate
asset output roots retain `task-submissions/<task-name>`. The launcher reads the
original package's local assets, not an alternate download directory.

Follow the skill's [validation layers](../.agents/skills/create-searchswe-task/references/validation.md):
Compose rendering, builds, verifier known-good and negative cases, and an
end-to-end trial with a configured coding model when authorized. Use a fresh
`--output` for each trial. Inspect the model's trajectory, submitted artifacts,
scores and judge health, then use that feedback to refine ambiguous instructions,
missing resources, inconsistent limits or grading defects. Recheck affected
validation layers and rerun the model when changes affect its task or scoring,
within the agreed budget. A valid low score alone does not justify easing the
task or rerunning an unchanged setting. Record findings, resulting changes (or
why none were needed), and the final evaluated revision. The skill's
[model-evaluation workflow](../.agents/skills/create-searchswe-task/references/model-evaluation.md)
defines this feedback loop and its stopping conditions.

Before the trial, the authoring agent checks which credentials the chosen model,
task APIs and judges require. If any are missing, it must tell the contributor
the exact variable names, their purpose, and where to configure them locally,
using [`.env.example`](../.env.example) and the [evaluation guide](evaluation.md).
Reuse existing authorized credentials; never ask for key values in chat or a
PR. Wait for configuration before starting the dependent run, while continuing
independent checks. Report unavailable runtime evidence explicitly.

Static checks alone do not prove solvability or safe grading. Report actual
commands, results, resource requirements and unrun layers. Enable **Allow edits
from maintainers** on the PR; if unavailable, the contributor makes the agreed
promotion commits in the same PR.

### CI and trust boundaries

The unprivileged `pull_request` and `push` workflow checks formal packages and
all submissions, including malformed or incomplete paths. With `--base`, it
also inspects every commit and both sides of merge history: submission paths
must be flat, paths cannot be reused, and each newly added formal task needs a
same-name, whole-package pure rename from its submission in this PR. Reviewed
renames of packages already formal on the base are recognized as existing-task
changes. New formal tasks require actual authors; existing author records remain.

Submission checks reuse release structure, asset pin/hash, secret, file-size
and Git-ignore checks, and parse Python, shell and Compose YAML without running
task code. Install PyYAML for the YAML check; Docker Compose rendering is separate.
`review-stage` may pass while submissions exist. Before merging, run
`python scripts/check_submission.py --merge-ready`: it rejects remaining
submissions and checks formal package syntax and obsolete references.

CI executes no GPU/API/container task trials. Repository tests are PR-controlled
code: use read-only permissions, no secrets and no persisted checkout credentials.
Never execute unreviewed PR code via `pull_request_target` with secrets or share
an official HF token. Review and separately authorize credentialed/runtime tests
in a disposable trusted environment.

## 3. Maintainer promotion in the same PR

Use [maintain-searchswe-task](../.agents/skills/maintain-searchswe-task/SKILL.md)
for gh review, audit and merge checks. Repository `scripts/promote_task.py` and
`scripts/prepare_hf_upload.py` delegate to that portable skill; a separately
installed skill uses its own scripts with `--repo-root /path/to/checkout`.

Finish design, provenance/license, environment, verifier-isolation and runtime
review. Update against current main while preserving author history. Recheck
task-name collisions with the base and queued PRs before promotion and merge.
Promotion keeps the task name unchanged.

Start from a clean worktree/index. The helper never commits, pushes or publishes:

```bash
python scripts/promote_task.py rename task-submissions/example-search example-search --dry-run
python scripts/promote_task.py rename task-submissions/example-search example-search
git diff --cached --summary
# Operator creates the separate pure-rename commit:
git commit -m 'Promote example-search'
python scripts/promote_task.py finalize task-submissions/example-search example-search --dry-run
python scripts/promote_task.py finalize task-submissions/example-search example-search
```

Repeat independently for each task. Rename does only `git mv`. Finalize requires
HEAD to be that task's single-parent, 100%-identical whole-package rename commit.
It updates the submission path in tracked text and prints changed lines;
the task name and canonical identity stay unchanged. It refuses unsupported
binary rewrites and does not edit downloaded data. Review replacements, mounts,
images and external URLs; update task inventories/docs and GPU test inventories
as needed. A name collision must be resolved through review before promotion,
never by overwriting a package.

Publish approved new official assets, pin their merged SHA, then validate. Make
any reference, asset or integration changes in a separate finalization commit
in this same PR; an empty finalization commit is unnecessary. Every submission
must be promoted before merge. Use a **merge commit only**, preserving original
author and pure-rename commits; no squash/rebase merge.

```bash
python scripts/check_release.py
python scripts/check_submission.py --merge-ready
python -m unittest discover -s scripts/tests -p 'test_*.py'
git diff --check
git log --follow -- tasks/example-search/instruction.md
git blame tasks/example-search/instruction.md
```

Original commits and unmodified lines' blame survive this workflow. GitHub file
lists/history may display renames differently; contributor statistics also
depend on account-linked email and reachability from the default branch.
Repository owners separately configure required review, resolved conversations,
current-base/queue checks and `review-stage`/`merge-ready` statuses. This workflow
does not configure remote protections or CODEOWNERS. Re-review each changed head;
resolve unavailable branch editing with the contributor, keeping the same PR.

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

### Task name: additive official publication, then GitHub merge

After task-name approval and promotion, change only the new task's dataset source
repo/filename to `search-swe/Search-SWE` and `tasks/<task-name>/...`. Preserve
original model repo pins and bundled metadata. Prepare **only new data files**
in `/path/to/new-data/tasks/<task-name>/...`, at the exact asset sizes/hashes.
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
  --task-path tasks/example-search --new-data /path/to/new-data \
  --output /path/to/upload-staging
```

Official asset staging requires a promoted package at `tasks/<task-name>`.

The offline helper verifies hashes and safe paths for new files, rejects
collisions and symlinks, and stages those files with a merged manifest that
preserves all existing records. Supply a trusted current manifest snapshot;
only the new data files are needed locally. Uploading is a separate step.
For a full dataset audit, `check_release.py --hf-data` checks the complete
inventory against a local dataset copy.

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
    create_pr=True, commit_message='Add example-search inputs and provenance',
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
main. Preserve existing tasks' pinned revisions and published assets.
