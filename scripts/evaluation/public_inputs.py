"""Make declared public, read-only task inputs readable after checkout/restore."""

import os
from pathlib import Path
import stat
import tomllib

import yaml


def prepare_public_inputs(document, environment_directory):
    """Run after final Compose security validation, before build/up.

    Only sources also declared read-only in the agent's main service qualify.
    Hidden verifier inputs, credentials and writable submission mounts are never
    selected. Keep file contents, ownership, write bits and executable intent.
    """
    if environment_directory is None:
        return
    environment = Path(environment_directory).absolute()
    if environment.name not in {"environment", "tests"}:
        return
    task = environment.parent
    agent_compose = task / "environment/docker-compose.yaml"
    if not (task / "task.toml").is_file() or not agent_compose.is_file():
        return
    config = tomllib.loads((task / "task.toml").read_text())
    if config.get("metadata", {}).get("public_inputs_readable") is not True:
        return
    agent = yaml.safe_load(agent_compose.read_text())

    def public_mount(mount):
        return (isinstance(mount, dict) and mount.get("type") == "bind"
                and mount.get("read_only") is True
                and str(mount.get("target", "")).startswith("/task/"))

    declared = set()
    for mount in agent.get("services", {}).get("main", {}).get("volumes", []):
        if public_mount(mount) and "${" not in mount.get("source", ""):
            source = Path(os.path.abspath(task / "environment" / mount["source"]))
            # Never treat task-root, tests/, authoring/ or external paths as public.
            if any(source.is_relative_to(task / name) and source != task / name
                   for name in ("environment", "data", "models")) or source == task / "models":
                declared.add((source, mount["target"]))

    changes = {}
    for mount in document.get("services", {}).get("main", {}).get("volumes", []):
        if not public_mount(mount):
            continue
        source = Path(mount["source"])
        if (source, mount["target"]) not in declared:
            continue
        if any(parent.is_symlink() for parent in (source, *source.parents)):
            raise ValueError(f"Public input must not traverse symlinks: {source}")
        pending = [source]
        while pending:
            path = pending.pop()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            directory = stat.S_ISDIR(info.st_mode)
            if not (directory or stat.S_ISREG(info.st_mode)) or mode & 0o7000:
                raise ValueError(f"Unsupported public input file type/mode: {path}")
            readable = mode | 0o444 | (0o111 if directory or mode & 0o111 else 0)
            if mode != readable:
                if not directory and info.st_nlink != 1:
                    raise ValueError(f"Cannot change permissions of hardlinked public input: {path}")
                changes[path] = readable
            if directory:
                pending.extend(path.iterdir())
    for path, mode in changes.items():
        path.chmod(mode, follow_symlinks=False)
