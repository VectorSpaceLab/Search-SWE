"""Inspect a checkout and fast-forward its configured Git upstream."""

import os
from contextlib import contextmanager, suppress
from pathlib import Path
import shutil
import subprocess
import tomllib
import uuid

from . import __version__
from .repository import check_compatibility, checkout_version, compatible_version


def git(root, *arguments, required=True):
    # Capture Git output: remote URLs and credential-helper errors can contain secrets.
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Git operation timed out; check repository access and network connectivity.") from error
    if result.returncode and required:
        raise ValueError(f"Git {arguments[0]} failed; inspect this checkout with Git and resolve access, network or file conflicts.")
    return result.stdout.strip() if result.returncode == 0 else None


def git_state(root):
    if not shutil.which("git"):
        return None
    top = git(root, "rev-parse", "--show-toplevel", required=False)
    if top is None or Path(top).resolve() != root.resolve():
        return None
    return {
        "revision": git(root, "rev-parse", "HEAD"),
        "branch": git(root, "symbolic-ref", "--quiet", "--short", "HEAD", required=False),
        "upstream": git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", required=False),
        "dirty": bool(git(root, "status", "--porcelain", "--untracked-files=normal")),
        "shallow": git(root, "rev-parse", "--is-shallow-repository") == "true",
    }


def info(root):
    try:
        check_compatibility(root)
        error = None
    except ValueError as exception:
        error = str(exception)
    return {"cli_version": __version__, "checkout": str(root),
            "checkout_version": checkout_version(root), "compatible": error is None,
            "compatibility_error": error,
            "task_count": sum(1 for _ in (root / "tasks").glob("*/task.toml")),
            "git": git_state(root)}


def pending_operation(root):
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer"):
        path = Path(git(root, "rev-parse", "--git-path", name))
        if (path if path.is_absolute() else root / path).exists():
            return True
    return False


def task_names(root, revision):
    paths = git(root, "ls-tree", "-r", "--name-only", revision, "--", "tasks/")
    return {parts[1] for line in paths.splitlines()
            if len(parts := line.split("/")) == 3 and parts[2] == "task.toml"}


@contextmanager
def fetched_revision(root, remote, merge_ref):
    # FETCH_HEAD is shared by every fetch in this checkout. Pin this operation's
    # result in its own ref, including while checking compatibility and merging.
    ref = f"refs/search-swe/update-{uuid.uuid4().hex}"
    try:
        git(root, "fetch", "--no-tags", "--no-recurse-submodules", "--", remote, f"{merge_ref}:{ref}")
        yield git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    finally:
        with suppress(OSError, ValueError):
            git(root, "update-ref", "-d", ref, required=False)


def update(root, *, check=False):
    state = git_state(root)
    if state is None:
        raise ValueError("Update requires Git and a Git checkout at the selected repository root; select one with --repo.")
    if state["branch"] is None:
        raise ValueError("Checkout has a detached HEAD; switch to the branch you want to update, then retry.")
    if not state["upstream"]:
        raise ValueError("This branch has no upstream; configure its tracking branch with Git, then retry.")
    in_progress = pending_operation(root)
    if not check and (state["dirty"] or in_progress):
        raise ValueError("Checkout has local changes or an unfinished Git operation. Resolve them before updating; use update --check to inspect available updates.")
    branch = state["branch"]
    remote = git(root, "config", "--get", f"branch.{branch}.remote")
    merge_ref = git(root, "config", "--get", f"branch.{branch}.merge")
    if not merge_ref.startswith("refs/heads/"):
        raise ValueError("The upstream must track a branch; configure its tracking branch with Git.")
    with fetched_revision(root, remote, merge_ref) as target:
        ahead, behind = map(int, git(root, "rev-list", "--left-right", "--count",
                                   f"{state['revision']}...{target}").split())
        try:
            project = tomllib.loads(git(root, "show", f"{target}:pyproject.toml"))["project"]
            version = project.get("version") if project.get("name") == "search-swe" else None
        except (ValueError, KeyError, TypeError, AttributeError):
            version = None
        compatible = (compatible_version(version) and
                      git(root, "cat-file", "-e", f"{target}:scripts/evaluation/run_task.py", required=False) is not None)
        before, after = task_names(root, state["revision"]), task_names(root, target)
        status = "diverged" if ahead and behind else "available" if behind else "ahead" if ahead else "up-to-date"
        if behind and not compatible:
            status = "incompatible"
        report = {"checkout": str(root), "branch": branch, "upstream": state["upstream"],
                  "cli_version": __version__, "checkout_version": checkout_version(root),
                  "target_version": version if isinstance(version, str) else "unknown",
                  "compatible": compatible, "before": state["revision"], "target": target,
                  "ahead": ahead, "behind": behind, "dirty": state["dirty"],
                  "git_operation_in_progress": in_progress, "status": status, "updated": False,
                  "tasks_added": sorted(after - before), "tasks_removed": sorted(before - after),
                  "task_count_before": len(before), "task_count_after": len(after)}
        if check:
            return report
        if behind and not compatible:
            raise ValueError(f"Upstream checkout {report['target_version']} is incompatible with CLI {__version__}; install a matching CLI before updating. Checkout files were preserved.")
        if ahead and behind:
            raise ValueError("Local and upstream histories have diverged; reconcile them with Git before updating.")
        if behind:
            if git_state(root) != state or pending_operation(root):
                raise ValueError("Checkout changed while checking updates; inspect its state and retry.")
            git(root, "merge", "--ff-only", "--no-autostash",
                "--no-overwrite-ignore", "--no-edit", "--no-stat", target)
            report.update(status="updated", updated=True, checkout_version=checkout_version(root))
        return report


def display(result, *, checking=False):
    print(f"Checkout: {result['checkout']}")
    print(f"CLI: {result['cli_version']}; checkout: {result['checkout_version']}")
    if "updated" not in result:
        print(f"Tasks: {result['task_count']}; compatible: {result['compatible']}")
        if state := result["git"]:
            print(f"Branch: {state['branch'] or 'detached HEAD'}; upstream: {state['upstream'] or 'unset'}")
            print(f"Revision: {state['revision']}; local changes: {state['dirty']}; shallow: {state['shallow']}")
        else:
            print("Git: unavailable or this directory is not a Git checkout root")
        if result["compatibility_error"]:
            print(result["compatibility_error"])
        return
    print(f"Branch: {result['branch']}; upstream: {result['upstream']}")
    print(f"Status: {result['status']}; {result['behind']} upstream commits, {result['ahead']} local commits")
    print(f"Target checkout: {result['target_version']}; compatible: {result['compatible']}")
    for label, key in (("Added tasks", "tasks_added"), ("Removed tasks", "tasks_removed")):
        if result[key]:
            print(f"{label}: {', '.join(result[key])}")
    if checking:
        print("Check only; checkout files were not changed.")
        if result["dirty"] or result["git_operation_in_progress"]:
            print("Resolve local changes or the unfinished Git operation before updating.")
        elif result["status"] == "available":
            print("Run search-swe update to apply this fast-forward.")
    elif result["updated"]:
        print(f"Updated to {result['target'][:12]}; {result['task_count_after']} tasks. Use search-swe list to explore them.")
