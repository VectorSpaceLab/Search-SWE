# Asset publication (separate authorization)

Read-only metadata/hash/license review and offline staging do not authorize uploads.
Do not log tokens or change authentication without approval. All paths and account
names below are examples to replace, not assigned identities.

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
python "$SKILL_DIR/scripts/prepare_hf_upload.py" --repo-root "$REPO" \
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
