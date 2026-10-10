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

Create each package directly at `tasks/<task-name>/` in your contribution branch.
Choose a concise description with at most five lowercase hyphen-separated words,
starting with an ASCII letter and otherwise using letters/digits. The `task-`
prefix and `all` are reserved. Check `tasks/` on the current base and active PRs
for name collisions. Set `task.name` to `search-swe/<task-name>`. A PR may contain
multiple uniquely named tasks.

Describe the task's goal, starting state and measured outcomes.
CPU is the default; choose `--hardware gpu` for actual GPU execution. Repeat
`--author` for coauthors. Use actual authors in `task.toml`, not only “Search-SWE”,
and a Git email associated with your GitHub account (or its noreply address).
Co-authored-by trailers supplement original commits and task authors.

The scaffold provides the package structure, writing prompts and a verifier that
fails closed. Complete the instructions, assets, environment and grader before
runtime validation. Revise existing tasks in place. Keep credentials, downloaded
inputs/models, job outputs and author-only solutions outside Git, and isolate
verifier inputs from agents.

## 2. Develop, evaluate and refine

Development assets may live in a personal public temporary HF dataset with
redistribution permission, manifest, provenance and license. Pin its immutable
40-character commit SHA in `assets.json`. Official data will use
`tasks/<task-name>/...`; model files retain their original repository pins.
See [asset contribution and publication](#asset-contribution-and-publication).

```bash
python scripts/check_tasks.py tasks/example-search
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python .agents/skills/create-searchswe-task/scripts/test_scaffold_task.py
git diff --check
python scripts/download_assets.py --task example-search --dry-run
# After approving the download budget:
python scripts/download_assets.py --task example-search
python scripts/download_assets.py --task example-search --verify-only
python scripts/run_task.py --task example-search \
  --agent pi --model deepseek/deepseek-flash --dry-run
```

Use `--task <task-name>` for downloads and local trials. The downloader's
`--task all` selects every package under `tasks/` in the current checkout.
`--task-path tasks/<task-name>` also accepts a canonical repository-relative
path. Jobs default to `jobs/<task-name>`; alternate asset output roots contain
`<task-name>/`. The launcher reads the package's local assets.

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

Static checks cover package structure and source syntax. Record runtime
commands, results, resource requirements and any unrun validation layers. Enable
**Allow edits from maintainers** on the PR where available; otherwise agree on
contributor-applied review fixes in the same PR.

### CI and trust boundaries

The unprivileged `pull_request` and `push` workflow checks every package under
`tasks/`, including incomplete or malformed directories. `check_tasks.py` reuses
release structure, asset pin/hash, secret, file-size and Git-ignore checks, and
parses Python, shell and Compose YAML without running task code. With `--base`,
it additionally requires actual authors for newly added tasks while preserving
existing author records, including reviewed package renames.

`review-stage` accepts pinned personal development datasets. Before merging,
`python scripts/check_tasks.py --merge-ready` requires dataset sources in
`search-swe/Search-SWE`, under `tasks/<task-name>/`, at immutable commit SHAs.
Model files retain their original repository pins. Maintainers also verify that
the official HF changes have merged and that runtime evidence covers the final
revision. Install PyYAML for static Compose parsing; render Compose separately.

CI runs static checks and repository tests with read-only permissions and no
secrets or persisted checkout credentials. Repository tests are PR-controlled
code. Review and separately authorize credentialed runtime tests in a disposable
trusted environment; run GPU/API/container trials there.

## 3. Review, publish and merge

Use [maintain-searchswe-task](../.agents/skills/maintain-searchswe-task/SKILL.md)
for gh review, task audit and merge checks. Finish design, provenance/license,
environment, verifier-isolation and runtime review. Update against current main
while preserving author history, and check task names against the base and queued
PRs. Apply review fixes, asset pins and directly necessary documentation or
inventory changes to the task package in the same PR.

Publish approved official inputs using the
[asset workflow](#asset-contribution-and-publication), then pin the merged HF SHA
and verify downloads. `scripts/prepare_hf_upload.py` delegates to the portable
maintainer skill; a separately installed skill uses its own helper with
`--repo-root /path/to/checkout`.

```bash
python scripts/check_release.py
python scripts/check_tasks.py --merge-ready --base FULL_PR_BASE_SHA
python -m unittest discover -s scripts/tests -p 'test_*.py'
git diff --check
git log --follow -- tasks/example-search/instruction.md
git blame tasks/example-search/instruction.md
```

Use a **merge commit** to preserve original author commits and unmodified lines'
attribution. Re-review each changed head and verify required checks for the
current head and base. Repository owners configure required reviews, resolved
conversations, current-base/queue checks and `review-stage`/`merge-ready` statuses.
After the merge, verify the resulting tree, official asset pins and author
history. GitHub contributor statistics also depend on account-linked email and
reachability from the default branch.

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
print(commit.oid)  # Pin this full SHA in task assets.json.
PY
```

Use this personal repo, its dataset-relative filenames, size/hash, and printed
immutable SHA in `assets.json`. Select the task by name with the downloader and
launcher for development validation. Keep the temporary repo accessible through
review and publication; retire it after official pinned downloads are verified.

### Official publication, then GitHub merge

After task and asset review, change only the new task's dataset source
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

Stage assets from the reviewed package at `tasks/<task-name>`.

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
cache and run release and merge-ready checks. Commit the verified asset pins
in the task PR, then merge the GitHub contribution. Preserve existing tasks'
pinned revisions and published assets.
