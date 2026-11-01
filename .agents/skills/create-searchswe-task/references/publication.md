# Asset publication (separate authorization)

Read-only metadata/hash/license review and offline staging do not authorize uploads.
Do not log tokens or change authentication without approval. All paths and account
names below are examples to replace, not assigned identities.

Existing public upstream HF datasets may remain the final source without an
official mirror. Pin the full 40-hex commit SHA, exact filename, size and SHA-256;
verify downloads and review provenance and usage terms before merging. Use this
publication workflow only when new hosting is needed, such as for processed
inputs or an approved archive. Review redistribution rights before any upload.

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
review and any publication; retire it only after no released task depends on it
and replacement pinned downloads are verified.

### Official publication, then GitHub merge

After task and asset review, verify and retain existing upstream and official pins.
For files selected for official publication, map their source repo/filename to
`search-swe/Search-SWE` and `tasks/<task-name>/...`, preserving original model
pins and bundled metadata.
Prepare **only new data files** in `/path/to/new-data/tasks/<task-name>/...`, at
the exact asset sizes/hashes. Changed bytes use a new official filename, keeping
earlier published assets available. Tasks whose data is already published can
proceed directly to final validation.

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
python scripts/assets/prepare_hf_upload.py \
  --official-manifest /path/to/official-snapshot/manifest.json \
  --task-path tasks/example-search --new-data /path/to/new-data \
  --output /path/to/upload-staging
```

Stage assets from the reviewed package at `tasks/<task-name>`.

The offline helper verifies hashes and safe paths for new files and preserves
all existing manifest records. References to published files must match their
recorded sizes and hashes; only additions are copied to staging. Conflicting
paths, duplicate references and symlinks fail validation. Supply a trusted
current manifest snapshot and only the new data files locally. Uploading is a
separate step.
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
