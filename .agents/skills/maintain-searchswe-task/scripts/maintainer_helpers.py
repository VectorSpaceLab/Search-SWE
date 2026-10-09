"""Offline promotion and additive HF staging; no network or automatic commits.

This is the implementation shared by the portable skill and repository CLIs.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tomllib

SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
SUBMISSION = re.compile(rf"task-submissions/({SLUG})/([12])-x-([1-9][0-9]*)")
FORMAL = re.compile(r"task-[12]-[1-9][0-9]*")

def safe_path(root, value):
    """Accept a canonical repo-relative path, never symlinks (even internal ones)."""
    root = root.resolve()
    value = str(value)
    path = Path(value)
    if (not value or path.is_absolute() or "\\" in value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError(f"Expected canonical repository-relative path: {value}")
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Symlink is not allowed: {current}")
    return current

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


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout

def promote(repo, source, target_id, phase, dry_run=False):
    repo = checked_path(repo)
    if phase not in ("rename", "finalize"):
        raise ValueError("Unknown promotion phase")
    match = SUBMISSION.fullmatch(source)
    if not match or not FORMAL.fullmatch(target_id):
        raise ValueError("Use task-submissions/<first-name-slug>/<1|2>-x-<positive-ordinal> and task-<1|2>-<positive-number>")
    if target_id.split("-")[1] != match[2]:
        raise ValueError("Task category mismatch")
    src = safe_path(repo, source)
    target = safe_path(repo, f"tasks/{target_id}")
    old_id = f"task-{match[2]}-x-{match[3]}"
    if git(repo, "status", "--porcelain"):
        raise ValueError("Promotion requires a clean worktree and index; commit reviewed work first")
    if phase == "rename":
        if not src.is_dir() or target.exists():
            raise ValueError("Source must exist and target must not exist; refusing overwrite")
        no_symlinks(src)
        config = tomllib.loads((src / "task.toml").read_text())
        if config.get("task", {}).get("name") != f"search-swe/{old_id}":
            raise ValueError("Source temporary task name does not match category")
        print(f"git mv {source} tasks/{target_id}")
        if not dry_run:
            target.parent.mkdir(exist_ok=True)
            git(repo, "mv", "--", source, f"tasks/{target_id}")
        print("STOP: review and commit ONLY this pure rename; then run finalize with the same source and target.")
        return
    if src.exists() or not target.is_dir():
        raise ValueError("Finalize requires the source to have been renamed")
    no_symlinks(target)
    # HEAD itself must be the operator's separate pure rename commit. No state file.
    parents = git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 2:
        raise ValueError("Finalize requires a single-parent pure rename HEAD commit")
    fields = git(repo, "diff", "--name-status", "-z", "-M100%", "HEAD^", "HEAD").strip("\0").split("\0")
    renamed = set()
    for index in range(0, len(fields), 3):
        chunk = fields[index:index + 3]
        if (len(chunk) != 3 or chunk[0] != "R100" or not chunk[1].startswith(source + "/")
                or chunk[2] != f"tasks/{target_id}/" + chunk[1][len(source) + 1:]):
            raise ValueError("HEAD must contain only 100% identical source-to-target renames")
        renamed.add(chunk[2])
    tracked = set(filter(None, git(repo, "ls-files", "-z", "--", f"tasks/{target_id}").split("\0")))
    if not tracked or renamed != tracked:
        raise ValueError("Pure rename commit must include every tracked package file")
    config = tomllib.loads((target / "task.toml").read_text())
    if config.get("task", {}).get("name") != f"search-swe/{old_id}":
        raise ValueError("Expected the unchanged temporary task name after rename")
    changes = []
    text_suffixes = {".md", ".toml", ".json", ".yaml", ".yml", ".sh", ".py", ".txt", ".cfg", ".ini"}
    for name in sorted(tracked):
        path = repo / name
        if old_id in path.relative_to(target).as_posix():
            raise ValueError(f"Manual filename review required: {name}")
        raw = path.read_bytes()
        if old_id.encode() not in raw and source.encode() not in raw:
            continue
        if path.suffix not in text_suffixes and path.name not in ("Dockerfile", ".gitignore", ".dockerignore"):
            raise ValueError(f"Manual review required for nonstandard text file: {name}")
        text = raw.decode("utf-8")
        updated = text.replace(source, f"tasks/{target_id}").replace(old_id, target_id)
        if old_id in updated or source in updated:
            raise ValueError(f"Temporary reference remains: {name}")
        changes.append((path, updated))
        for number, (before, after) in enumerate(zip(text.splitlines(), updated.splitlines()), 1):
            if before != after:
                print(f"{name}:{number}: {before} -> {after}")
    if not dry_run:
        for path, updated in changes:
            path.write_text(updated)
    print("Temporary package references remaining after planned changes: 0.")
    print("Review every change, external asset paths/images and repository task inventories. "
          "Publish approved assets, pin the official SHA, validate, then commit finalization in this SAME PR.")


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
    if not FORMAL.fullmatch(task.name):
        raise ValueError("Assign the final task ID before preparing official publication")
    config = tomllib.loads((task / "task.toml").read_text())
    if config.get("task", {}).get("name") != f"search-swe/{task.name}":
        raise ValueError("Finalize task.toml before preparing official publication")
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


def promotion_main(default_repo=None):
    parser = argparse.ArgumentParser(description="Two-phase offline promotion; never commits or publishes")
    parser.add_argument("phase", choices=("rename", "finalize"))
    parser.add_argument("source")
    parser.add_argument("target_id")
    parser.add_argument("--repo-root", type=Path, default=default_repo, required=default_repo is None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        repo = checked_path(args.repo_root)
        promote(repo, args.source, args.target_id, args.phase, args.dry_run)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0

def upload_main(legacy=False):
    parser = argparse.ArgumentParser(description="Offline incremental HF staging; never uploads")
    parser.add_argument("--repo-root", type=Path, required=not legacy)
    parser.add_argument("--official-manifest", required=True, type=Path)
    parser.add_argument("--task-path", required=True, type=Path)
    parser.add_argument("--new-data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        # Legacy repository CLI accepted paths relative to cwd, or any absolute task.
        # Portable CLI always requires an explicit target root.
        task = args.task_path
        if args.repo_root is not None:
            repo = checked_path(args.repo_root)
            task = checked_path(repo / task)
            if not task.is_relative_to(repo):
                raise ValueError("Task must be inside --repo-root")
        count = prepare(args.official_manifest, task, args.new_data, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Prepared {count} new files and merged manifest; preserved old entries without downloading old data.")
    print("No upload performed. Review SOURCES.md, dataset card/license and .gitattributes; never delete old assets.")
    return 0
