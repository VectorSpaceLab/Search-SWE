# Downloading task data and models

[Documentation index](../README.md)

The CLI restores the selected tasks' assets automatically. Use this guide to
plan storage, prepare inputs in advance or restore a local copy. Install the host
tools as described in the [quick start](quickstart.md), then run the commands
below from the repository root.

## Commands

Download all fixed inputs for one task:

```bash
python scripts/assets/download_assets.py --task long-document-reranking
```

Download data or models separately:

```bash
python scripts/assets/download_assets.py --task all --kind data
python scripts/assets/download_models.py --task all
```

The model command uses the same downloader with `--kind models` by default.
It selects model entries from each task's `assets.json`. Multiple task names may
be passed after `--task`. `--task all` selects every package under `tasks/` in the
current checkout; `--task-path tasks/<task-name>` accepts a canonical
repository-relative path.

Preview the selected files, sources, and total size:

```bash
python scripts/assets/download_assets.py --task all --dry-run
```

## Disk space and cache locations

Before downloading, the CLI shows the task destination, Hugging Face cache,
estimated additional storage and free space, and stops if estimated capacity is
insufficient. Preview these estimates with `search-swe run TASK --dry-run`, or
obtain machine-readable details with:

```bash
python scripts/assets/download_assets.py --task long-document-reranking --plan
```

Task copies live in the selected checkout at `tasks/<task-name>/data` and
`models` according to each manifest. The cache is additional storage, normally
`~/.cache/huggingface/hub`. Set `HF_HUB_CACHE=/large-disk/hf-hub` in the shell or
the CLI's selected `.env` to change it; native downloader scripts use the shell
environment or `--cache-dir`. `HF_HOME` and `XDG_CACHE_HOME` also affect the
default cache path. Choose another checkout location for the task copies.

Estimates account for existing file sizes, reuse of shared cache sources and
atomic replacement of different-size target files. Requirements on the same
filesystem are summed. Checksums are verified during restoration; same-size
corruption may require extra repair space. Reserve additional capacity for
Docker images/builds, task scratch files and evaluation results.

## Directory layout

Downloads are restored relative to the task root:

```text
tasks/<task-name>/
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

`long-pdf-evidence` restores one shared PDF to `data/corpus/` and public queries and labels
to `data/validation/`. Both environments use the same PDF; only the Agent mounts
public validation. Hidden questions and relevance labels stay in `tests/data/`.

Compose configurations mount the required data and models read-only. The agent
receives public inputs; the verifier mounts the shared assets needed for
evaluation and loads hidden inputs from `tests/data/`. Hidden inputs are excluded
from the agent environment, but files published in the repository remain visible
to repository readers.

Generated indexes, trained weights, and other submission outputs follow the
artifact paths in `task.toml`. They are separate from the fixed input assets.

## Sources and fixed versions

Task data may be hosted in its public upstream HF repository or in
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
python scripts/assets/download_assets.py --task scientific-paper-qa long-pdf-evidence agentic-search \
  --local-data-dir ../hf-data
python scripts/validation/check_release.py --hf-data ../hf-data --verify-data
```

Local restoration verifies sizes and SHA-256 checksums. For task authoring and
checks on unpublished assets, see the
[contribution workflow](../contributing/tasks.md#validate-local-assets).

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
python scripts/assets/download_assets.py --task all --verify-only
```

If an existing file differs, the downloader reports an error. To replace it:

```bash
python scripts/assets/download_assets.py --task long-document-reranking --force
```

`--force` permits replacing invalid task files. Valid Hugging Face cache entries
are reused across tasks; an invalid cached file is redownloaded once and checked
again. In offline mode, invalid cached content produces an error so it can be
repaired during a later online run.

`--cache-dir /path/to/cache` selects the Hugging Face cache. `--local-files-only`
uses only already cached inputs. `--output-dir /path/to/tasks` restores task
directories elsewhere; pass the same output path when verifying that copy.
The standard launcher uses the selected package's assets in the repository,
not an alternate output directory.

The downloader uses Hugging Face login or `HF_TOKEN` when available. Public,
ungated downloads do not require your Agent or verifier API keys. For a host
proxy, configure your own standard `HTTP_PROXY`/`HTTPS_PROXY` environment
variables. The download scripts do not load `.env`; current task-runtime
allowlists reject `CONTAINER_PROXY` because a general proxy would bypass
destination filtering.
