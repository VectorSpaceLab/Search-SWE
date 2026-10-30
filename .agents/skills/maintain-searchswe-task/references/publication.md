# Asset publication (separate authorization)

Read-only metadata/hash/license review and offline staging do not authorize uploads.
Do not log tokens or change authentication without approval. All paths and account
names below are examples to replace, not assigned identities.

## Choose the publication work

For each dataset-backed asset, verify its published source, immutable revision,
filename, size and SHA-256, and review provenance and usage terms. Public upstream
HF datasets may remain the final source without an official mirror. Retain
verified upstream and official pins. A PR using only verified published data can
proceed to final validation. Use the workflow below only for files selected for
official hosting, such as new processed inputs or an approved archive of upstream
data; review redistribution rights before uploading. Tasks using only model
repositories or bundled metadata follow their applicable validation checks.

For a mix of existing and new data, stage only the additions. If published bytes
need to change, choose a new official filename so the earlier asset and its
manifest record remain available. Preserve existing sources and pins for
unchanged files throughout the process.

## HF authentication and access

Before authenticated downloads, upload or HF PR merge, run `hf auth whoami`
in the same host environment used for publication. Reuse an existing authorized
login or `HF_TOKEN`; report only identity, authentication status and relevant
access findings. If `hf` is missing, point the operator to the trusted checkout's
`pyproject.toml` and host setup: `python -m pip install -e .` from that checkout.

If authentication is missing or expired, the coding agent must explicitly remind
the maintainer to configure their own HF account locally and identify the step
that needs it. Provide these operator-run commands:

```bash
hf auth login
hf auth whoami
```

The operator can instead supply `HF_TOKEN` through their local process environment
or secret manager. These publication scripts do not load the repository `.env`.
An exported `HF_TOKEN` takes precedence over the saved login; if the account is
unexpected, ask the operator to correct that local configuration. Keep token
values in local authentication storage: never request them in chat or PRs, print
them, or include them in command arguments or captured artifacts.

Confirm access for the intended operation: opening a community PR requires an
authenticated account permitted to contribute there; merging or directly writing
to `search-swe/Search-SWE` requires the publishing maintainer's dataset write
access and a credential scope that permits that action. `whoami` confirms the
effective identity; check account and token permissions separately. If access
is insufficient, explain the missing permission and ask the maintainer to resolve
it locally or involve another authorized publisher.

Ask the operator to confirm when configuration is ready, then recheck identity
and relevant access before the dependent operation. While waiting, continue
public ungated downloads, local hash checks, staging and metadata review that
can run with the available access. Authentication setup and publication use the
existing session-authorized scope. See the HF [authentication guide](https://huggingface.co/docs/huggingface_hub/en/guides/cli#hf-auth-login),
[token permissions](https://huggingface.co/docs/hub/security-tokens) and
[environment variables](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables#hf_token).

## 1. Download the contributor's pinned data

Set `REPO` to the isolated checkout of the reviewed PR head and `SKILL_DIR` to
this installed skill. Use independently reviewed target download tools. The
contributor's `tasks/<task-name>/assets.json` identifies each source dataset,
exact filename, immutable revision, size and SHA-256 hash.
Keep these original sources until their files have been downloaded and verified.

Within the authorized download budget, use a fresh external workspace:

```bash
set -euo pipefail
task_name=example-search
publication_root=/path/to/new-publication-workspace
mkdir -- "$publication_root"
cp -- "$REPO/tasks/$task_name/assets.json" "$publication_root/development-assets.json"
python "$REPO/scripts/download_assets.py" --task "$task_name" --kind data --dry-run
python "$REPO/scripts/download_assets.py" --task "$task_name" --kind data \
  --output-dir "$publication_root/downloads" --cache-dir "$publication_root/development-cache"
python "$REPO/scripts/download_assets.py" --task "$task_name" --kind data \
  --output-dir "$publication_root/downloads" --verify-only
```

Files are restored under `$publication_root/downloads/<task-name>/<entry.path>`.
The downloader uses each original source revision and checks its bytes. Public,
ungated development data can be downloaded with maintainer-owned access; the
contributor's token is unnecessary. Retrieve its dataset card, `SOURCES.md`,
manifest and applicable license files at the same pinned revisions using
`hf_hub_download`. Review provenance and redistribution terms for each dataset.
If approved dataset-backed entries also live under `models/`, restore those with
`--kind models` as needed; model-repository sources and bundled metadata retain
their original pins and paths.

Publish only approved redistributable inputs. Keep private evaluation answers,
credentials, job outputs and task code outside the upload set. Missing files,
hash mismatches or unresolved redistribution rights need resolution before
publication. The saved development manifest records the original source mapping.

## 2. Prepare official paths from the verified files

For each new dataset file approved for official publication, choose its destination
under `tasks/<task-name>/...`. Preserve the asset's task-relative `path`, size,
hash and permissions. Copy the verified bytes to
`$publication_root/new-data/<official-filename>`, creating parent directories.
For example:

| Item | Example |
| --- | --- |
| Task-relative asset path | `data/corpus.jsonl` |
| Verified local file | `downloads/example-search/data/corpus.jsonl` |
| Official dataset filename | `tasks/example-search/data/corpus.jsonl` |
| Staging input file | `new-data/tasks/example-search/data/corpus.jsonl` |

In the isolated PR checkout, update those entries' `source.repo_id` to
`search-swe/Search-SWE`, `source.repo_type` to `dataset`, and `source.filename`
to the chosen official filename. Set `source.revision` to `null` during local
staging; after publication it receives the actual merged official SHA. Keep this
intermediate manifest local until that SHA and fresh downloads are verified.
All other entries, including original model sources, remain intact. The
`new-data` directory contains exactly the mapped new dataset files for this task.

## 3. Stage the official manifest and provenance

Fetch the small current official manifest snapshot and metadata, not the whole
dataset. Use your own authorized HF account in the trusted publication workspace:

```bash
python - "$publication_root/official-snapshot" <<'PY'
from pathlib import Path
import shutil
import sys
from huggingface_hub import HfApi, hf_hub_download
repo = 'search-swe/Search-SWE'
sha = HfApi().repo_info(repo_id=repo, repo_type='dataset').sha
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False)
(out / 'BASE_SHA').write_text(sha)
for name in ('manifest.json', 'README.md', 'SOURCES.md', '.gitattributes'):
    shutil.copyfile(hf_hub_download(repo_id=repo, repo_type='dataset', revision=sha, filename=name), out / name)
print(sha)
PY
python "$SKILL_DIR/scripts/prepare_hf_upload.py" --repo-root "$REPO" \
  --official-manifest "$publication_root/official-snapshot/manifest.json" \
  --task-path "tasks/$task_name" --new-data "$publication_root/new-data" \
  --output "$publication_root/upload-staging"
```

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

For a GitHub PR containing several tasks, use a separate workspace for each task.
When publishing one task at a time, refresh the official snapshot after each HF
merge so subsequent manifests preserve the earlier additions.

## 4. Publish and merge the official HF change

After upload authorization, submit a Hugging Face **community PR** using your
own account. The `parent_commit` binds it to the reviewed official snapshot:

```bash
python - "$publication_root" "$task_name" <<'PY'
from pathlib import Path
import sys
from huggingface_hub import HfApi
root = Path(sys.argv[1])
result = HfApi().upload_folder(
    repo_id='search-swe/Search-SWE', repo_type='dataset',
    folder_path=root / 'upload-staging',
    parent_commit=(root / 'official-snapshot/BASE_SHA').read_text().strip(),
    create_pr=True, commit_message=f'Add {sys.argv[2]} inputs and provenance',
)
print(result.pr_url)
PY
```

Link the HF PR and GitHub task PR. A maintainer must review manifest preservation,
hashes, sources and licensing. If official HEAD changes, refresh the snapshot,
regenerate/review the merged manifest and coordinate the HF PR update; never
replace a newer manifest with a stale one.

After authorized HF review and merge, record the actual official merge commit
containing the approved files. If community PRs are unavailable, a maintainer
with official dataset write permission may publish the same reviewed staging
folder using their own authorized account and record its resulting official
commit. Contributors keep their personal credentials; official write access
stays with the publishing maintainer.

## 5. Pin the official revision and update the GitHub PR

Replace the local staging `null` revisions with the published official 40-hex
commit SHA, retaining the verified official repo IDs and filenames. Use the
official merged commit, rather than a community PR head or a moving branch.
Verify these new sources with a fresh output directory and cache:

```bash
python "$REPO/scripts/download_assets.py" --task "$task_name" --kind data \
  --output-dir "$publication_root/official-downloads" --cache-dir "$publication_root/official-cache"
python "$REPO/scripts/download_assets.py" --task "$task_name" --kind data \
  --output-dir "$publication_root/official-downloads" --verify-only
```

Apply the same verification to any additional dataset-backed model entries
published in this change. Compare the final mapping and hashes with the saved
development manifest, then run release and merge-ready checks. Follow
[finalization](finalization.md#commit-asset-pins-to-the-contributors-pr-branch)
to commit `assets.json` and push it to the contributor's PR source branch. Once
the updated GitHub head passes review and required checks, merge that PR.
Keep the development dataset accessible until official downloads are verified;
preserve existing tasks' published assets and pinned revisions.

HF API usage follows the official [download](https://huggingface.co/docs/huggingface_hub/guides/download)
and [upload](https://huggingface.co/docs/huggingface_hub/guides/upload) guides.
