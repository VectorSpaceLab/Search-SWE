# Downloading task data and models

[Documentation index](../README.md)

`search-swe run` restores and verifies the selected tasks' inputs automatically.
Use this guide for disk planning, standalone preparation, local copies and repair.
Run standalone download commands from the checkout root after [installation](quickstart.md).

## Commands

Preview the files and total size, then download a task's fixed inputs:

```bash
python scripts/assets/download_assets.py --task long-document-reranking --dry-run
python scripts/assets/download_assets.py --task long-document-reranking
```

| Option | Purpose |
| --- | --- |
| `--task NAME [NAME ...]` | Select one or more tasks; `--task all` selects every package |
| `--task-path tasks/NAME` | Select a repository-relative task directory |
| `--kind data` / `--kind models` | Download only that asset kind |
| `--plan` | Print machine-readable disk estimates |
| `--cache-dir PATH` | Select a Hugging Face cache |
| `--local-files-only` | Use cached inputs only |
| `--output-dir PATH` | Restore under `PATH/<task-name>/`; use the same path when verifying |

`scripts/assets/download_models.py` uses the same downloader with `--kind models`.
The standard launcher reads assets from the task package in the checkout;
alternate output directories are for staging or inspection.

## Disk space and cache locations

The CLI shows task destinations, cache location, estimated additional space
and free capacity before downloading. Preview with `search-swe run TASK --dry-run`.

| Location | Contents / configuration |
| --- | --- |
| `<checkout>/tasks/<task-name>/data/` and `models/` | Task copies specified by `assets.json`; choose the checkout's disk accordingly |
| `~/.cache/huggingface/hub` by default | Additional HF cache; set `HF_HUB_CACHE` in the shell or CLI `.env` to relocate it |
| Jobs and Docker storage | Logs, outputs, images and writable task storage; reserve capacity separately |

`HF_HOME` and `XDG_CACHE_HOME` also affect the default cache. Standalone download
scripts use shell variables or `--cache-dir`; they do not load `.env`.

Estimates reuse existing files/shared cache sources and include atomic
replacement of different-size files. Requirements on one filesystem are summed;
insufficient capacity stops the CLI. Checksums are verified during restoration,
so same-size corruption may need extra repair space. Leave additional room for
Docker builds, task scratch files and results.

## Directory layout

| Task-relative path | Purpose |
| --- | --- |
| `assets.json` | File paths, immutable sources, sizes, hashes and permissions |
| `data/`, `models/` | Downloaded inputs, excluded from Git and Docker build contexts |
| `model-metadata/` | Small bundled model metadata, restored through the manifest |
| `tests/data/` | Hidden evaluation queries, labels and references, isolated from the agent; large files may also be restored through `assets.json` |

Agent and verifier mounts expose the inputs each phase needs. Repository files
remain visible to repository readers even when excluded from the agent container.
Generated indexes, trained weights and other submissions use the artifact paths
in `task.toml`, separately from fixed inputs.

The downloader applies manifest permissions, including `0700` directories and
`0600` files for private verifier models. Restore as a host user distinct from
the verifier's submission UID 10001; permissions must be prepared on the host
before read-only mounts are used.

## Sources and fixed versions

`assets.json` records exact filenames, immutable HF revisions, sizes and SHA-256
hashes. Data can come from public upstream datasets or
[search-swe/Search-SWE](https://huggingface.co/datasets/search-swe/Search-SWE);
model weights retain their original repository pins. Bundled metadata uses a
local source under `model-metadata/`.

Downloads use HF login or `HF_TOKEN` when needed; public ungated assets need no
coding-agent or judge key. For a host download proxy, set
`HTTP_PROXY`/`HTTPS_PROXY`. Container runtime networking is configured separately
in the [network guide](network.md).

## Restoring from a local data directory

Restore an existing `hf-data` copy without downloading:

```bash
python scripts/assets/download_assets.py --task long-document-reranking --local-data-dir ../hf-data
python scripts/validation/check_release.py --hf-data ../hf-data --verify-data
```

Restoration checks sizes and SHA-256. During task development, add
`--allow-unpublished` to the release check for staged inputs. Before submitting,
publish them, pin their immutable revisions and rerun without that flag. See
[task contributions](../contributing/tasks.md) for the authoring workflow.

## Verification and resuming

Existing valid files are reused; new downloads are checksum-verified before
atomic replacement. Interrupted downloads can reuse the HF cache on retry.

```bash
python scripts/assets/download_assets.py --task long-document-reranking --verify-only
python scripts/assets/download_assets.py --task long-document-reranking --force
```

`--verify-only` checks without downloading. `--force` replaces invalid
manifest-owned files while reusing valid cache entries. A corrupt cache entry
is downloaded again and checked once; offline runs report invalid content for
repair during a later online run. Normal CLI runs perform this verified repair
automatically.
