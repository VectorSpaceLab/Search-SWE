#!/usr/bin/env python3
"""Build the gateway from checksum-pinned APKs with an offline Docker build.

An explicit --download permits fetching missing public APKs; standard host curl
proxy configuration is honored. Images are preloaded, never pulled or pushed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import uuid
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "environments/egress"
sys.path.insert(0, str(ROOT))
from scripts.egress.build_audit import runtime_inventory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args, **kwargs):
    return subprocess.run(list(args), check=True, text=True, timeout=kwargs.pop("timeout", 60), **kwargs)


def inspect(image):
    return json.loads(command("docker", "image", "inspect", image, capture_output=True).stdout)[0]


def stage_archives(lock, cache, context, download=False):
    cache.mkdir(parents=True, exist_ok=True)
    context.mkdir()
    for name, expected in lock["archives"].items():
        if Path(name).name != name or not name.endswith(".apk"):
            raise ValueError("Invalid pinned APK filename")
        cached = cache / name
        target = context / name
        if not cached.exists():
            if not download:
                raise ValueError(f"Missing cached APK: {name}; use --download explicitly")
            command("curl", "--fail", "--silent", "--show-error", "--proto", "=https", "--max-time", "120",
                    "--output", str(target), lock["repository"] + name, timeout=125)
            if digest(target) != expected:
                raise ValueError(f"Downloaded APK checksum mismatch: {name}")
            shutil.copyfile(target, cached)
        shutil.copyfile(cached, target)
        if digest(target) != expected:
            raise ValueError(f"Cached APK checksum mismatch: {name}")


def build(args):
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    manifest = {"status": "building", "requested_tag": args.tag}
    probe = "searchswe-runtime-build-" + uuid.uuid4().hex[:12]
    try:
        base = inspect(args.component_image)
        if base.get("Os") != "linux" or base.get("Architecture") != "amd64":
            raise ValueError("Only Linux amd64 component images are supported")
        labels = base["Config"].get("Labels") or {}
        if (labels.get("org.search-swe.egress.component") != "gost-x-0.10.9-searchswe-1"
                or labels.get("org.search-swe.egress.patch-sha256") != digest(SOURCE / "patch_gost.py")):
            raise ValueError("Component image is not from the pinned current patch")
        if args.component_image.startswith("sha256:"):
            raise ValueError("BuildKit needs a preloaded local image name, not a bare image ID")
        if subprocess.run(["docker", "image", "inspect", args.tag], capture_output=True, timeout=15).returncode == 0:
            raise ValueError("Use a new gateway image tag; do not overwrite an existing build")
        context = work / "image"
        context.mkdir()
        sources = {}
        for name in ("Dockerfile", "gateway.py", "entrypoint.sh", "network-policy", "runtime.lock.json"):
            data = (SOURCE / name).read_bytes()
            (context / name).write_bytes(data)
            sources[name] = hashlib.sha256(data).hexdigest()
        lock = json.loads((context / "runtime.lock.json").read_text())
        manifest.update(base_image_id=base["Id"], sources=sources, archives=lock["archives"])
        stage_archives(lock, args.cache_dir.resolve(), context / "packages", args.download)
        with (work / "build.log").open("w") as log:
            command("docker", "build", "--pull=false", "--network=none", "--build-arg", "COMPONENT_IMAGE=" + args.component_image,
                    "--build-arg", "GATEWAY_SOURCE_SHA=" + sources["gateway.py"],
                    "--build-arg", "RUNTIME_LOCK_SHA=" + sources["runtime.lock.json"], "-t", args.tag, str(context),
                    stdout=log, stderr=subprocess.STDOUT, timeout=600)
        image = inspect(args.tag)
        manifest["image_id"] = image["Id"]
        if (inspect(args.component_image)["Id"] != base["Id"]
                or image["RootFS"]["Layers"][:len(base["RootFS"]["Layers"])] != base["RootFS"]["Layers"]):
            raise ValueError("Component image changed during runtime build")
        # Inspect an unstarted container. Package verification needs no image
        # process, namespace startup, credentials, capabilities or network.
        command("docker", "create", "--pull", "never", "--name", probe, "--label", "searchswe.runtime-build=" + probe,
                "--network", "none", "--cap-drop", "ALL", "--read-only", "--security-opt", "no-new-privileges:true",
                "--entrypoint", "/bin/true", image["Id"], capture_output=True)
        for source, name in (("/lib/apk/db/installed", "installed"), ("/etc/alpine-release", "alpine-release"),
                             ("/usr/share/searchswe-egress/runtime.json", "runtime.json")):
            target = work / name
            command("docker", "cp", probe + ":" + source, str(target), capture_output=True)
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                raise ValueError("Unexpected runtime metadata file")
        records = [dict(line.split(":", 1) for line in record.splitlines() if ":" in line)
                   for record in (work / "installed").read_text().split("\n\n")]
        actual = {v["P"]: v["V"] for v in records if "P" in v}
        if (actual != lock["installed"] or (work / "alpine-release").read_text().strip() != lock["alpine_release"]
                or digest(work / "runtime.json") != sources["runtime.lock.json"]):
            raise ValueError("Installed runtime package/lock drift")
        manifest["runtime"] = {"packages": actual, "alpine_release": lock["alpine_release"]}
        (work / "runtime-packages.json").write_text(json.dumps(runtime_inventory((work / "installed").read_text()), indent=2) + "\n")
        manifest["runtime_inventory_sha256"] = digest(work / "runtime-packages.json")
        for name, expected in sources.items():
            if digest(SOURCE / name) != expected:
                raise ValueError("Runtime source changed during build")
        manifest.update(status="passed", image_id=image["Id"])
    except Exception as error:
        manifest.update(status="failed", error_class=type(error).__name__)
        raise
    finally:
        try:
            response = subprocess.run(["docker", "container", "inspect", probe], capture_output=True, text=True, timeout=15)
            if response.returncode == 0:
                info = json.loads(response.stdout)[0]
                if info["Config"].get("Labels", {}).get("searchswe.runtime-build") != probe:
                    raise RuntimeError("Runtime probe ownership mismatch")
                command("docker", "rm", "-f", probe, capture_output=True)
            elif "No such" not in response.stderr:
                raise RuntimeError("Could not verify runtime probe cleanup")
        except Exception:
            manifest["status"] = "cleanup_error"
            raise
        finally:
            (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component-image", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--download", action="store_true")
    build(parser.parse_args())
