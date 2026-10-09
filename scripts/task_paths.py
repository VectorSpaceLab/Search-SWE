"""Explicit task selection and symlink-free repository boundaries."""

from pathlib import Path
import re

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


def select_task(root, value):
    task = safe_path(root, value)
    rel = task.relative_to(root.resolve()).as_posix()
    if not SUBMISSION.fullmatch(rel) and not re.fullmatch(r"tasks/task-[a-z0-9]+(?:-[a-z0-9]+)*", rel):
        raise ValueError("--task-path must name tasks/<task-id> or task-submissions/<first-name-slug>/<1|2>-x-<positive-ordinal>")
    if not (task / "task.toml").is_file():
        raise ValueError(f"Missing task.toml: {rel}")
    no_symlinks(task)
    return task


def task_key(root, task):
    """Keep submission namespaces in output paths; equal temporary IDs cannot collide."""
    rel = task.relative_to(root.resolve())
    return Path(*rel.parts[1:]) if rel.parts[0] == "tasks" else rel
