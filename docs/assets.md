# Downloading task data and models

Use Python 3.12 or newer. Install the download dependency in your host environment:

```bash
python -m pip install -r scripts/requirements-assets.txt
```

## Commands

Download all fixed inputs for one task:

```bash
python scripts/download_assets.py --task task-2-1
```

Download data or models separately:

```bash
python scripts/download_assets.py --task all --kind data
python scripts/download_models.py --task all
```

The model command uses the same downloader with `--kind models` by default.
It selects model entries from each task's `assets.json`. Multiple task IDs may
be passed after `--task`.

Preview the selected files, sources, and total size:

```bash
python scripts/download_assets.py --task all --dry-run
```

Use the preview to estimate disk requirements. Allow additional space for the
Hugging Face cache; the downloader copies cached files into the task directories.

## Directory layout

Downloads are restored relative to the task root:

```text
tasks/<task-id>/
├── instruction.md
├── task.toml
├── assets.json           # Asset paths, sources, sizes, and checksums
├── data/                 # Downloaded corpus, vectors, training and validation data
├── models/               # Downloaded fixed models, when required
├── model-metadata/       # Bundled model metadata, when required
├── environment/          # Agent Dockerfile, Compose configuration, starter code, docs
└── tests/                # Verifier environment and grading code
    └── data/             # Hidden evaluation queries, labels, and reference results
```

`data/` and `models/` are excluded from Git. Keeping them outside `environment/`
and `tests/` keeps large assets out of Harbor's build contexts and content hashes.
Their contents are verified separately against `assets.json`.

Task 1-4 also restores held-out PDFs to `data/verifier/corpus/`. Its Agent
mounts only `data/corpus/` and `data/validation/`; only the verifier mounts the
held-out corpus. These PDF files are downloadable assets, while held-out
questions and relevance labels stay in `tests/data/`.

Compose configurations mount the required data and models read-only. The agent
receives public inputs; the verifier mounts the shared assets needed for
evaluation and loads hidden inputs from `tests/data/`. Hidden inputs are excluded
from the agent environment, but files published in the repository remain visible
to repository readers.

Generated indexes, trained weights, and other submission outputs follow the
artifact paths in `task.toml`. They are separate from the fixed input assets.

## Sources and fixed versions

Task data is hosted in
[search-swe/Search-SWE](https://huggingface.co/datasets/search-swe/Search-SWE).
Model weights come from their original model repositories. Each task's
`assets.json` is the source of truth for its files and immutable dataset or
model revisions; use `--dry-run` to inspect the selected sources.

Each entry in the manifest's `files` list records a task-relative `path`,
`size_bytes`, `sha256`, and `source`. A source identifies either a Hugging Face
repository, revision, and filename, or a `local_path` under `model-metadata/`.
Bundled metadata is restored and verified by the same downloader.

## Restoring from a local data directory

If you maintain a local `hf-data` copy, you can restore task assets from it
without network access:

```bash
python scripts/download_assets.py --task task-1-3 task-1-4 task-2-4 \
  --local-data-dir ../hf-data
python scripts/check_release.py --hf-data ../hf-data --verify-data
```

Local restoration verifies sizes and SHA-256 checksums. For maintainers adding
unpublished data, the staging check accepts `--allow-unpublished` together with
`--hf-data`; it still checks mappings and data integrity. Before publishing the
code, upload the dataset files, pin their immutable commit in `assets.json`,
and run the release check without `--allow-unpublished`. Remote downloads fail
explicitly if a dataset revision is unset.

The downloader applies file permissions from each entry's `mode` and private
directory permissions from `directory_modes`. Private verifier models use
directories with mode `0700` and files with mode `0600`; other downloaded files
are readable by the submission user. Download as a host user distinct from the
verifier's submission UID 10001 to preserve that separation. Prepare permissions
on the host before running, because the container mounts are read-only.

## Verification and resuming

Existing files are skipped only after their size and SHA-256 match. Newly
downloaded files are checked before an atomic replacement into their final
location. Partial network downloads can reuse the Hugging Face cache on retry.

To verify without downloading:

```bash
python scripts/download_assets.py --task all --verify-only
```

If an existing file differs, the downloader reports an error. To replace it:

```bash
python scripts/download_assets.py --task task-2-1 --force
```

`--cache-dir /path/to/cache` selects the Hugging Face cache. `--local-files-only`
uses only already cached inputs. `--output-dir /path/to/tasks` restores task
directories elsewhere; pass the same output path when verifying that copy.
The standard launcher uses the repository's own `tasks/` directory.

The downloader uses Hugging Face login or `HF_TOKEN` when available. Public,
ungated downloads do not require your Agent or verifier API keys. For a host
proxy, configure your own standard `HTTP_PROXY`/`HTTPS_PROXY` environment
variables; `.env` and `CONTAINER_PROXY` belong to the task launcher and are not
loaded by the download scripts.

## Checking a release package

From a Git checkout, check task structure, fixed asset sources, bundled metadata,
Git exclusions, and accidental large files or common credential patterns:

```bash
python scripts/check_release.py
```

If you maintain a local Hugging Face staging directory, also compare its file
inventory with the task manifests and verify the data checksums:

```bash
python scripts/check_release.py --hf-data ../hf-data --verify-data
```

These are static file checks. Container builds and benchmark runs are validated
separately.
