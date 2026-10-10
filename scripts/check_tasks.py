#!/usr/bin/env python3
"""Static, credential-free task checks; never import or run task code."""

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from check_release import check_release
from download_assets import REPO, read_manifest
from task_paths import no_symlinks, safe_path, select_task


def discover(repo):
    root = safe_path(repo, "tasks")
    no_symlinks(root)
    # Include incomplete directories and nested packages so both fail validation.
    return sorted(set(root.glob("*/")) | {p.parent for p in root.rglob("task.toml")})


def git_names(repo, *args):
    """Run a NUL-delimited Git pathname query without shell interpolation."""
    return [name for name in subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
    ).stdout.decode("utf-8", errors="surrogateescape").split("\0") if name]


def git_object_exists(repo, commit, path):
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"], cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def renamed_packages(repo, base):
    """Recognize existing packages renamed in this PR."""
    fields = git_names(repo, "diff", "--name-status", "-z", "--find-renames=50%",
                       f"{base}...HEAD", "--", "tasks")
    renamed, index = set(), 0
    while index < len(fields):
        status = fields[index]
        index += 1
        source = fields[index]
        index += 1
        if not status.startswith(("R", "C")):
            continue
        target = fields[index]
        index += 1
        old, new = Path(source), Path(target)
        if (status.startswith("R") and len(old.parts) == len(new.parts) == 3
                and old.name == new.name == "task.toml"
                and git_object_exists(repo, base, source)
                and not git_object_exists(repo, "HEAD", str(old.parent))):
            renamed.add(new.parent.name)
    return renamed


def check_package(repo, task, *, require_authors=True, merge_ready=False):
    errors = []
    try:
        task = select_task(repo, task.relative_to(repo).as_posix())
        config = tomllib.loads((task / "task.toml").read_text())
        expected = task.name
        if config.get("task", {}).get("name") != f"search-swe/{expected}":
            errors.append(f"Expected task name search-swe/{expected}")
        authors = config.get("task", {}).get("authors", [])
        if require_authors and (not authors or any(not isinstance(a, dict) or not isinstance(a.get("name"), str)
                              or a["name"].strip().lower() in ("", "search-swe", "your name", "author") for a in authors)):
            errors.append("Actual task authors are required")
        shared, _ = check_release(repo, packages=[task])
        errors.extend(shared)
        if merge_ready:
            for entry in read_manifest(task)["files"]:
                source = entry.get("source", {})
                if source.get("repo_type") == "dataset" and "local_path" not in source:
                    if source.get("repo_id") != "search-swe/Search-SWE":
                        errors.append(f"{entry['path']}: merge-ready data must use search-swe/Search-SWE")
                    if not source.get("filename", "").startswith(f"tasks/{task.name}/"):
                        errors.append(f"{entry['path']}: official data must use tasks/{task.name}/")
        # Only parse source files; do not execute Python, shell, Docker or verifiers.
        candidates = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", str(task.relative_to(repo))],
            cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.split("\0")
        for name in filter(None, candidates):
            path = repo / name
            if not path.is_file():
                continue
            if path.stat().st_size >= 100 * 1024**2:
                continue  # Shared checks already reject large files.
            try:
                text = path.read_text()
            except UnicodeError:
                continue
            if path.suffix == ".py":
                ast.parse(text, filename=name)
            if path.suffix == ".sh":
                result = subprocess.run(["bash", "--noprofile", "--norc", "-n", str(path)],
                                        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
                if result.returncode:
                    errors.append(f"{name}: shell syntax error: {result.stderr.strip()}")
        import yaml
        for phase in ("environment", "tests"):
            overlay = yaml.safe_load((task / phase / "docker-compose.yaml").read_text())
            if not isinstance(overlay, dict) or not isinstance(overlay.get("services"), dict) or "main" not in overlay["services"]:
                errors.append(f"{phase}: Compose overlay must define services.main")
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.CalledProcessError) as error:
        errors.append(str(error))
    except ImportError:
        errors.append("Compose syntax checks require PyYAML: python -m pip install PyYAML")
    except Exception as error:
        # Safe YAML parse errors should be a failed check, not an omitted layer.
        errors.append(f"Static parse failed: {error}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_path", nargs="?", help="Repository-relative tasks/<task-name>; otherwise check all")
    parser.add_argument("--merge-ready", action="store_true", help="Require official dataset sources and pinned revisions")
    parser.add_argument("--base", help="Full PR base commit; require actual authors for new tasks")
    args = parser.parse_args()
    errors = []
    try:
        tasks = [safe_path(REPO, args.task_path)] if args.task_path else discover(REPO)
        if not tasks:
            errors.append("No task packages found")
        base, renamed = None, set()
        if args.base:
            if not re.fullmatch(r"[0-9a-f]{40}", args.base):
                raise ValueError("--base requires a full commit SHA")
            base = subprocess.run(["git", "merge-base", args.base, "HEAD"], cwd=REPO,
                                  check=True, capture_output=True, text=True).stdout.strip()
            renamed = renamed_packages(REPO, base)
        for task in tasks:
            relative = task.relative_to(REPO).as_posix()
            require_authors = (task.name not in renamed and not git_object_exists(
                REPO, base or "HEAD", f"{relative}/task.toml"))
            errors.extend(f"{relative}: {error}" for error in check_package(
                REPO, task, require_authors=require_authors, merge_ready=args.merge_ready))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        errors.append(str(error))
    for error in errors:
        print(f"ERROR: {error}")
    stage = "Merge-ready" if args.merge_ready else "Review-stage"
    print(f"{stage} task static check: {len(errors)} errors.")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
