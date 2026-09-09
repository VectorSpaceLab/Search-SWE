#!/usr/bin/env python3
"""Restore fixed Search-SWE inputs from pinned Hugging Face revisions."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
TASKS = tuple(sorted(path.parent.name for path in (REPO / "tasks").glob("*/task.toml")))


def relative_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"Invalid asset path: {value!r}")
    return Path(*path.parts)


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def matches(path, entry):
    return (path.is_file() and path.stat().st_size == entry["size_bytes"]
            and checksum(path) == entry["sha256"])


def read_manifest(task):
    manifest = json.loads((task / "assets.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError(f"Unsupported manifest schema: {task.name}")
    seen = set()
    for entry in manifest["files"]:
        rel = relative_path(entry["path"])
        if not rel.parts or rel.parts[0] not in ("data", "models") or len(rel.parts) < 2:
            raise ValueError(f"Asset must be under data/ or models/: {rel}")
        if rel in seen:
            raise ValueError(f"Duplicate asset: {rel}")
        seen.add(rel)
        if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            raise ValueError(f"Invalid asset size: {rel}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"Invalid SHA-256: {rel}")
        if entry.get("mode", "0644") not in ("0600", "0644"):
            raise ValueError(f"Unsupported file permissions: {rel}")
    for name, mode in manifest.get("directory_modes", {}).items():
        rel = relative_path(name)
        if len(rel.parts) < 2 or rel.parts[0] != "models" or mode != "0700":
            raise ValueError(f"Unsupported private model directory: {name}")
    return manifest


def destination_path(task_output, rel):
    target = task_output / rel
    if target.is_symlink() or not target.resolve().is_relative_to(task_output.resolve()):
        raise ValueError(f"Asset destination must stay inside its task directory: {rel}")
    return target


def prepare_directories(task_output, rel, directory_modes):
    task_output.mkdir(parents=True, exist_ok=True)
    for parent in reversed(rel.parents):
        if parent == Path("."):
            continue
        path = task_output / parent
        new = not path.exists()
        path.mkdir(exist_ok=True)
        mode = directory_modes.get(parent.as_posix())
        if mode or new:
            path.chmod(int(mode or "0755", 8))


def obtain_source(task, entry, args):
    source = entry.get("source", {})
    if "local_path" in source:
        local = task / relative_path(source["local_path"])
        if not local.resolve().is_relative_to(task.resolve()) or not matches(local, entry):
            raise ValueError(f"Bundled model metadata is missing or invalid: {entry['path']}")
        return local
    if not re.fullmatch(r"[0-9a-f]{40}", source.get("revision") or ""):
        raise ValueError(f"No published fixed revision for {task.name}/{entry['path']}")
    if source.get("repo_type") not in ("dataset", "model"):
        raise ValueError(f"Invalid Hugging Face source for {entry['path']}")
    relative_path(source["filename"])
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise ValueError("Install dependencies: python -m pip install -r scripts/requirements-assets.txt") from error
    return Path(hf_hub_download(
        repo_id=source["repo_id"], repo_type=source["repo_type"],
        filename=source["filename"], revision=source["revision"],
        cache_dir=args.cache_dir, local_files_only=args.local_files_only,
        force_download=args.force and not args.local_files_only,
    ))


def restore(task, task_output, entry, directory_modes, args):
    rel = relative_path(entry["path"])
    target = destination_path(task_output, rel)
    if matches(target, entry):
        if not args.verify_only:
            prepare_directories(task_output, rel, directory_modes)
            target.chmod(int(entry.get("mode", "0644"), 8))
        return "verified"
    if args.verify_only:
        raise ValueError(f"Missing or invalid asset: {task.name}/{rel}")
    if target.exists() and not args.force:
        raise ValueError(f"Existing file differs from the manifest: {task.name}/{rel}; use --force to replace it")
    source = obtain_source(task, entry, args)
    prepare_directories(task_output, rel, directory_modes)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-", delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as origin:
                shutil.copyfileobj(origin, stream, length=8 * 1024 * 1024)
        if not matches(temporary, entry):
            raise ValueError(f"Downloaded file failed size/SHA-256 verification: {task.name}/{rel}")
        temporary.chmod(int(entry.get("mode", "0644"), 8))
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "downloaded" if "repo_id" in entry.get("source", {}) else "restored metadata"


def main(default_kind="all"):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", nargs="+", required=True, choices=("all", *TASKS))
    parser.add_argument("--kind", choices=("all", "data", "models"), default=default_kind)
    parser.add_argument("--output-dir", type=Path, default=REPO / "tasks", help="Parent of task directories")
    parser.add_argument("--cache-dir", type=Path, help="Hugging Face cache directory")
    parser.add_argument("--force", action="store_true", help="Replace files whose checksums differ")
    parser.add_argument("--local-files-only", action="store_true", help="Use cached downloads without network access")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List selected assets without reading or downloading their contents")
    mode.add_argument("--verify-only", action="store_true", help="Check local file sizes and SHA-256 without downloading")
    args = parser.parse_args()
    tasks = TASKS if "all" in args.task else tuple(dict.fromkeys(args.task))
    count, size, failures = 0, 0, []
    for name in tasks:
        task = REPO / "tasks" / name
        manifest = read_manifest(task)
        for entry in manifest["files"]:
            kind = "data" if entry["path"].startswith("data/") else "models"
            if args.kind not in ("all", kind):
                continue
            count += 1
            size += entry["size_bytes"]
            label = f"{name}/{entry['path']}"
            if args.dry_run:
                source = entry.get("source", {})
                origin = source.get("local_path") or f"{source.get('repo_id')}@{source.get('revision') or 'UNPUBLISHED'}"
                print(f"{label}  {entry['size_bytes']} bytes  {origin}")
                continue
            try:
                status = restore(task, args.output_dir / name, entry, manifest.get("directory_modes", {}), args)
                print(f"{status}: {label}", flush=True)
            except Exception as error:
                failures.append(label)
                print(f"ERROR {label}: {error}", file=sys.stderr, flush=True)
    print(f"Selected {count} files ({size / 1024**3:.2f} GiB); failures: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
