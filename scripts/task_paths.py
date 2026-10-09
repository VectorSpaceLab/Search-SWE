"""Explicit task selection and symlink-free repository boundaries."""

from pathlib import Path
import re

# Keep this contract in sync with the two independently installable skill helpers.
TASK_NAME = r"(?!all(?:/|$))(?!task-)[a-z][a-z0-9]*(?:-[a-z0-9]+){0,4}"
FORMAL = re.compile(TASK_NAME)
SUBMISSION = re.compile(rf"task-submissions/({TASK_NAME})")


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
    if not SUBMISSION.fullmatch(rel) and not re.fullmatch(rf"tasks/({TASK_NAME})", rel):
        raise ValueError("--task-path must name tasks/<task-name> or task-submissions/<task-name>; "
                         "use at most five lowercase hyphen-separated words, without a task- prefix")
    if not (task / "task.toml").is_file():
        raise ValueError(f"Missing task.toml: {rel}")
    no_symlinks(task)
    return task


def task_key(root, task):
    """Keep submission outputs separate from formal task outputs."""
    rel = task.relative_to(root.resolve())
    return Path(*rel.parts[1:]) if rel.parts[0] == "tasks" else rel
