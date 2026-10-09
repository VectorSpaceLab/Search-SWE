#!/usr/bin/env python3
"""List owned orphan manifests, or recover one after its host owner has exited.

Default is read-only. --remove stops/removes only resources with matching
instance AND Compose project labels, then removes that instance's private files.
It never removes images, host datasets, unrelated containers, or unowned volumes.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.egress.ownership import LABEL, ProjectLock, owner_root, read_manifest


def docker(*args):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True, timeout=30).stdout


def inventory(manifest):
    context = json.loads(docker("context", "inspect"))[0]
    endpoint = (None if os.environ.get("DOCKER_CONTEXT") else os.environ.get("DOCKER_HOST")) or context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("unix://"):
        raise ValueError("Orphan cleanup supports only the local Unix-socket Docker daemon")
    daemon_id = json.loads(docker("info", "--format", "{{json .ID}}"))
    if not daemon_id or daemon_id != manifest.get("daemon_id"):
        raise ValueError("Docker daemon identity mismatch or legacy manifest; refusing recovery")
    resources = []
    for kind in ("container", "network", "volume"):
        flags = ["-aq"] if kind == "container" else ["-q"]
        ids = docker(kind, "ls", *flags, "--filter", f"label={LABEL}={manifest['instance']}").split()
        for identity in ids:
            info = json.loads(docker(kind, "inspect", identity))[0]
            labels = info["Config"].get("Labels", {}) if kind == "container" else info.get("Labels", {})
            if labels.get(LABEL) != manifest["instance"] or labels.get("com.docker.compose.project") != manifest["project"]:
                raise ValueError("Resource ownership mismatch; nothing may be removed")
            gateway = kind == "container" and labels.get("com.docker.compose.service") == "harbor-docker-egress-control-sidecar"
            if gateway and info["Config"]["Image"] != manifest["image"]:
                raise ValueError("Gateway image ownership mismatch")
            resources.append({"kind": kind, "id": identity, "gateway": gateway})
    container_ids = {r["id"] for r in resources if r["kind"] == "container"}
    for resource in resources:
        if resource["kind"] == "network":
            info = json.loads(docker("network", "inspect", resource["id"]))[0]
            if not set(info.get("Containers", {})) <= container_ids:
                # docker ls emits short IDs; compare exact inspect IDs below.
                full_ids = {json.loads(docker("container", "inspect", identity))[0]["Id"] for identity in container_ids}
                if not set(info.get("Containers", {})) <= full_ids:
                    raise ValueError("Owned network includes an unrelated container")
    return resources


def recover(directory, remove=False):
    directory = Path(directory).absolute()
    manifest = read_manifest(directory)
    lock = ProjectLock(manifest["project"])
    try:
        resources = inventory(manifest)
        audit_paths = []
        if remove:
            # Fence by killing the trusted gateway before removing other actors.
            for resource in sorted(resources, key=lambda r: (not r["gateway"], r["kind"] != "container")):
                kind, identity = resource["kind"], resource["id"]
                # Recheck immediately before mutation, including project labels.
                if resource not in inventory(manifest):
                    raise ValueError("Resource ownership changed during recovery")
                if resource["gateway"]:
                    # Fence first, then preserve the controller's sanitized
                    # audit before deleting its Docker log. An audit I/O error
                    # leaves the stopped resource and manifest recoverable.
                    state = json.loads(docker("container", "inspect", identity))[0]
                    if state["State"]["Running"]:
                        docker("container", "kill", identity)
                    audit = docker("logs", identity)
                    fd, path = tempfile.mkstemp(prefix="recovery-audit-", suffix=".log", dir=directory.parent)
                    with os.fdopen(fd, "w") as stream:
                        stream.write(audit)
                        stream.flush()
                        os.fsync(stream.fileno())
                    parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                    audit_paths.append(path)
                docker(kind, "rm", *(["-f"] if kind == "container" else []), identity)
            if inventory(manifest):
                raise RuntimeError("Owned resources remain after recovery")
            if read_manifest(directory) != manifest:
                raise RuntimeError("Private manifest changed during recovery")
            shutil.rmtree(directory)
        return {"instance": manifest["instance"], "project": manifest["project"],
                "resources": resources, "removed": remove, "audit_paths": audit_paths}
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    if args.remove and args.directory is None:
        parser.error("--remove requires one explicit --directory")
    if args.directory is not None:
        print(json.dumps(recover(args.directory, args.remove), indent=2))
    else:
        rows = []
        for directory in sorted(owner_root().glob("instance-*")):
            manifest = read_manifest(directory)
            rows.append({"directory": str(directory), "instance": manifest["instance"], "project": manifest["project"]})
        print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
