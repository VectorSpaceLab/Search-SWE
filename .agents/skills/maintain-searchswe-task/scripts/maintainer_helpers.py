"""Offline additive HF staging; no network or automatic commits.

This is the implementation shared by the portable skill and repository CLIs.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tomllib

TASK_NAME = r"(?!all(?:/|$))(?!task-)[a-z][a-z0-9]*(?:-[a-z0-9]+){0,4}"
TASK_NAME_RE = re.compile(TASK_NAME)

def no_symlinks(path):
    if path.is_symlink() or any(item.is_symlink() for item in path.rglob("*")):
        raise ValueError(f"Task package must not contain symlinks: {path}")


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


def checked_path(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError(f"Parent traversal is not allowed: {path}")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Symlink is not allowed: {path}")
    return path

def prepare(snapshot, task, data, output):
    snapshot, task, data, output = map(checked_path, (snapshot, task, data, output))
    for tree in (task, data):
        no_symlinks(tree)
    if output.exists():
        raise ValueError("Upload output must not exist; refusing overwrite")
    if task.parent.name != "tasks" or not TASK_NAME_RE.fullmatch(task.name):
        raise ValueError("Task package must be at tasks/<task-name>")
    config = tomllib.loads((task / "task.toml").read_text())
    if config.get("task", {}).get("name") != f"search-swe/{task.name}":
        raise ValueError("task.toml name must match the task directory")
    if not data.is_dir() or output.is_relative_to(data) or output.is_relative_to(task):
        raise ValueError("Use a separate output directory and an existing new-data directory")
    manifest = json.loads(snapshot.read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Unsupported official manifest schema")
    old = set()
    for entry in manifest["files"]:
        name = entry["path"]
        rel = relative_path(name)
        if (rel.as_posix() != name or len(rel.parts) < 3 or rel.parts[0] != "tasks"
                or name in old or type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError(f"Invalid or duplicate official manifest record: {name}")
        old.add(name)
    additions = {}
    for entry in read_manifest(task)["files"]:
        source = entry.get("source", {})
        if source.get("repo_type") != "dataset" or source.get("repo_id") != "search-swe/Search-SWE":
            continue
        name = source["filename"]
        rel = relative_path(name)
        if rel.as_posix() != name or not name.startswith(f"tasks/{task.name}/"):
            raise ValueError(f"New data must be under tasks/{task.name}/: {name}")
        if name in old or name in additions:
            raise ValueError(f"Refusing dataset path collision: {name}")
        if not matches(data / rel, entry):
            raise ValueError(f"Missing data or size/SHA-256 mismatch: {name}")
        additions[name] = {"path": name, "size_bytes": entry["size_bytes"], "sha256": entry["sha256"]}
    actual = {p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file()}
    if not additions or actual != set(additions):
        raise ValueError("New-data directory must contain exactly the new task's official dataset files")
    merged = {**manifest, "files": [*manifest["files"], *[additions[n] for n in sorted(additions)]]}
    output.mkdir(parents=True)
    try:
        for name in sorted(additions):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(data / name, target)
        (output / "manifest.json").write_text(json.dumps(merged, indent=2) + "\n")
    except Exception:
        shutil.rmtree(output)
        raise
    return len(additions)


def upload_main(repository_cli=False):
    parser = argparse.ArgumentParser(description="Offline incremental HF staging; never uploads")
    parser.add_argument("--repo-root", type=Path, required=not repository_cli)
    parser.add_argument("--official-manifest", required=True, type=Path)
    parser.add_argument("--task-path", required=True, type=Path)
    parser.add_argument("--new-data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        # The repository CLI accepts paths relative to cwd, or absolute task paths.
        # Portable CLI always requires an explicit target root.
        task = args.task_path
        if args.repo_root is not None:
            repo = checked_path(args.repo_root)
            task = checked_path(repo / task)
            if not task.is_relative_to(repo):
                raise ValueError("Task must be inside --repo-root")
            relative = task.relative_to(repo)
            if len(relative.parts) != 2 or relative.parts[0] != "tasks":
                raise ValueError("Official publication requires tasks/<task-name> under --repo-root")
        count = prepare(args.official_manifest, task, args.new_data, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Prepared {count} new files and merged manifest; preserved existing manifest entries.")
    print("Review SOURCES.md, dataset card/license and .gitattributes before the authorized upload.")
    return 0
