#!/usr/bin/env python3
"""Static, credential-free submission checks; never import or run task code."""

import argparse
import ast
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from check_release import check_release
from download_assets import REPO
from task_paths import SUBMISSION, no_symlinks, safe_path, select_task


def discover(repo):
    root = safe_path(repo, "task-submissions")
    no_symlinks(root)
    # Include malformed paths and incomplete package directories, not just valid TOMLs.
    return sorted(set(root.glob("*/*/")) | {p.parent for p in root.rglob("task.toml")})


def submission_namespace(path):
    """Return a namespace from a canonical package path, rejecting unsafe history names."""
    if "\\" in path:
        raise ValueError(f"Unsafe task-submissions path: {path!r}")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe task-submissions path: {path!r}")
    if parts[0] != "task-submissions":
        raise ValueError(f"Expected task-submissions path: {path!r}")
    if len(parts) == 2 and parts[1] == "README.md":
        return None
    if len(parts) < 4 or not re.fullmatch(SUBMISSION, "/".join(parts[:3])):
        raise ValueError(f"Malformed task submission path in PR history: {path!r}")
    return parts[1]


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


def history_submission_audit(repo, base):
    """Inspect every commit and merge parent; return namespaces and reused task roots."""
    commits = subprocess.run(
        ["git", "rev-list", "--reverse", "--topo-order", f"{base}..HEAD"],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    namespaces = set()
    additions = {}
    for commit in commits:
        parents = subprocess.run(
            ["git", "show", "-s", "--format=%P", commit], cwd=repo,
            check=True, capture_output=True, text=True,
        ).stdout.split()
        changed = set()
        if parents:
            for parent in parents:
                changed.update(git_names(
                    repo, "diff-tree", "--no-commit-id", "-r", "--name-only",
                    "-z", "--no-renames", parent, commit, "--", "task-submissions",
                ))
        else:
            changed.update(git_names(
                repo, "diff-tree", "--root", "--no-commit-id", "-r",
                "--name-only", "-z", "--no-renames", commit, "--", "task-submissions",
            ))
        for name in changed:
            namespace = submission_namespace(name)
            if namespace is not None:
                namespaces.add(namespace)
            if (name.endswith("/task.toml") and git_object_exists(repo, commit, name)
                    and all(not git_object_exists(repo, parent, name) for parent in parents)):
                additions[name] = additions.get(name, 0) + 1
    return namespaces, sorted(name.rsplit("/", 1)[0]
                              for name, count in additions.items() if count > 1)


def check_package(repo, task, *, formal=False, require_authors=True):
    errors = []
    try:
        task = select_task(repo, task.relative_to(repo).as_posix())
        match = SUBMISSION.fullmatch(task.relative_to(repo).as_posix())
        if not formal and not match:
            raise ValueError("Not a submission path")
        config = tomllib.loads((task / "task.toml").read_text())
        expected = task.name if formal else f"task-{match[2]}-x-{match[3]}"
        category = re.fullmatch(r"task-([12])-(?:x-[1-9][0-9]*|[1-9][0-9]*)", expected)
        if category:
            kind = {"1": "create", "2": "optimize"}[category[1]]
            if config.get("metadata", {}).get("task_type") != kind:
                errors.append(f"Category {category[1]} requires metadata.task_type = {kind}")
        if config.get("task", {}).get("name") != f"search-swe/{expected}":
            errors.append(f"Expected task name search-swe/{expected}")
        authors = config.get("task", {}).get("authors", [])
        if require_authors and (not authors or any(not isinstance(a, dict) or not isinstance(a.get("name"), str)
                              or a["name"].strip().lower() in ("", "search-swe", "your name", "author") for a in authors)):
            errors.append("Actual task authors are required")
        shared, _ = check_release(repo, packages=[task])
        errors.extend(shared)
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
            ids = set(re.findall(r"\btask-[12]-(?:[1-9][0-9]*|x-[1-9][0-9]*)\b", text))
            if not formal and ids - {expected}:
                errors.append(f"{name}: unexpected task IDs {sorted(ids - {expected})}")
            if formal and any(re.fullmatch(r"task-[12]-x-[1-9][0-9]*", value) for value in ids):
                errors.append(f"{name}: temporary task ID remains")
            for ref in re.findall(r"task-submissions/[a-z0-9-]+/[12]-x-[1-9][0-9]*", text):
                if formal or ref != task.relative_to(repo).as_posix():
                    errors.append(f"{name}: another submission path: {ref}")
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


def check_submission(repo, task):
    return check_package(repo, task)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_path", nargs="?", help="Repository-relative submission; otherwise check all")
    parser.add_argument("--merge-ready", action="store_true", help="Fail if any submission task.toml remains")
    parser.add_argument("--base", help="Full PR base commit for contributor-namespace and new-formal-package checks")
    args = parser.parse_args()
    errors = []
    try:
        tasks = [safe_path(REPO, args.task_path)] if args.task_path else discover(REPO)
        for task in tasks:
            errors.extend(f"{task.relative_to(REPO)}: {error}" for error in check_submission(REPO, task))
        remaining = list((REPO / "task-submissions").rglob("task.toml"))
        current_namespaces = set()
        for task in discover(REPO):
            rel = task.relative_to(REPO).as_posix()
            if rel.startswith("task-submissions/"):
                try:
                    namespace = submission_namespace(rel + "/task.toml")
                    if namespace:
                        current_namespaces.add(namespace)
                except ValueError as error:
                    errors.append(str(error))
        if len(current_namespaces) > 1:
            errors.append(f"Submission tasks must use exactly one contributor namespace: {sorted(current_namespaces)}")
        if args.merge_ready and remaining:
            errors.append("Not merge-ready: submission task.toml remains; promote in the same PR")
        # Promotion must not remove the package's static validation coverage.
        if args.merge_ready:
            for config in sorted((REPO / "tasks").glob("*/task.toml")):
                errors.extend(f"{config.parent.relative_to(REPO)}: {error}" for error in
                              check_package(REPO, config.parent, formal=True, require_authors=False))
        if args.base:
            if not re.fullmatch(r"[0-9a-f]{40}", args.base):
                raise ValueError("--base requires a full commit SHA")
            added = subprocess.run(["git", "diff", "--no-renames", "--diff-filter=A", "--name-only", "-z",
                                    f"{args.base}...HEAD", "--", "tasks", "task-submissions"],
                                   cwd=REPO, check=True, capture_output=True).stdout.decode(
                                       "utf-8", errors="surrogateescape").split("\0")
            history_namespaces, reused_tasks = history_submission_audit(REPO, args.base)
            if len(history_namespaces) > 1:
                errors.append(f"PR task submissions must use exactly one contributor namespace: {sorted(history_namespaces)}")
            if reused_tasks:
                errors.append(f"Temporary task ordinals must not be reused in one PR: {reused_tasks}")
            added_formal = [name for name in filter(None, added)
                            if name.startswith("tasks/") and name.endswith("/task.toml")]
            if added_formal and len(history_namespaces) != 1:
                errors.append("New formal tasks require exactly one contributor submission namespace in PR history")
            for name in added_formal:
                errors.extend(check_package(REPO, (REPO / name).parent, formal=True))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        errors.append(str(error))
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Submission static check: {len(errors)} errors. "
          + ("Merge-ready tree required." if args.merge_ready else "Review-stage only; success does NOT mean merge-ready."))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
