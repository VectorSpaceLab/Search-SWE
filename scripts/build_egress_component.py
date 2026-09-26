#!/usr/bin/env python3
"""Build the patched GOST base used by build_egress_gateway.py.

Requires Go 1.26.8, curl, Docker and an already-built Harbor sidecar image.
Downloads are checksum pinned; work/output files never enter task containers.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import sys
from importlib.metadata import distribution


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.egress.build_audit import collect_notices, json_stream
from scripts.build_egress_gateway import stage_archives
SOURCES = {
    "gost-3.2.6": ("https://codeload.github.com/go-gost/gost/tar.gz/v3.2.6",
                   "79874354530b899576dd4866d3b1400651d0b17c1e7a90ad30c44686a0642600"),
    "x-0.10.9": ("https://codeload.github.com/go-gost/x/tar.gz/refs/tags/v0.10.9",
                 "5b3f2a97c047e4b90b24c5a6b3d147d1d1c0a38b900979daa5f94350db6bb6fb"),
}
LOCKS = {
    "go.mod": "baa2a2e9c290f98d0b2c8165f9ca13fad456b349c17989191da53150b33adef1",
    "go.sum": "023ebf43011ac2d3945e81b029b2b5cb11aa2fcbf913dbc08794b6eecb685806",
}

SECURITY_MINIMA = {'github.com/pion/dtls/v3': 'v3.1.4', 'github.com/quic-go/quic-go': 'v0.59.1', 'github.com/quic-go/webtransport-go': 'v0.11.1', 'golang.org/x/crypto': 'v0.56.0', 'golang.org/x/net': 'v0.56.0', 'golang.org/x/text': 'v0.39.0', 'google.golang.org/grpc': 'v1.83.2'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, **kwargs)


def inspect(image):
    return json.loads(command(["docker", "image", "inspect", image], capture_output=True).stdout)[0]


def build(args):
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    go = str(Path(shutil.which(args.go) or args.go).resolve())
    manifest = {"sources": SOURCES, "status": "building"}
    try:
        if command([go, "version"], capture_output=True).stdout.strip() != "go version go1.26.8 linux/amd64":
            raise ValueError("This component build currently requires Go 1.26.8 on Linux amd64")
        base = inspect(args.base_image)
        manifest["base_image_id"] = base["Id"]
        recipe = ROOT / "environments/egress/Dockerfile.component"
        recipe_bytes = recipe.read_bytes()
        apk_lock_path = ROOT / "environments/egress/component-apks.lock.json"
        apk_lock = json.loads(apk_lock_path.read_text())
        inputs = {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__).resolve(), ROOT / "scripts/egress/build_audit.py", ROOT / "scripts/build_egress_gateway.py", recipe, apk_lock_path)}
        manifest["build_source_sha256"] = inputs
        if base.get("Os") != "linux" or base.get("Architecture") != "amd64":
            raise ValueError("The component base must be Linux amd64")
        if args.base_image.startswith("sha256:"):
            raise ValueError("BuildKit requires a preloaded local base name, not a bare image ID")
        existing = subprocess.run(["docker", "image", "inspect", args.tag], capture_output=True, text=True, timeout=15)
        if existing.returncode == 0 or "No such image" not in existing.stderr:
            raise ValueError("Use a verified new component image tag; do not overwrite a previous build")
        manifest.update(base_rootfs=base["RootFS"], base_repo_digests=base.get("RepoDigests", []),
                        go_executable_sha256=sha(Path(go)), offline=args.offline)
        for name, (url, digest) in SOURCES.items():
            archive = cache / f"{name}.tar.gz"
            if not archive.exists():
                if args.offline:
                    raise ValueError(f"Missing offline source cache: {name}")
                temporary = work / f"{name}.download"
                command(["curl", "--fail", "--location", "--retry", "2", "--max-time", "180",
                         "--output", str(temporary), url], timeout=600)
                if sha(temporary) != digest:
                    raise ValueError(f"Source checksum mismatch: {name}")
                shutil.copyfile(temporary, archive)
            if sha(archive) != digest:
                raise ValueError(f"Cached source checksum mismatch: {name}")
            with tarfile.open(archive) as tar:
                # Pinned archives only; reject path traversal/special files too.
                for entry in tar.getmembers():
                    path = Path(entry.name)
                    if path.is_absolute() or ".." in path.parts or not (entry.isdir() or entry.isfile()):
                        raise ValueError("Unsupported source archive entry")
                tar.extractall(work, filter="data")
        patcher = ROOT / "environments/egress/patch_gost.py"
        patch_bytes = patcher.read_bytes()
        patch_digest = hashlib.sha256(patch_bytes).hexdigest()
        namespace = {"__name__": "egress_patch", "__file__": str(patcher)}
        exec(compile(patch_bytes, str(patcher), "exec"), namespace)
        namespace["apply"](work / "x-0.10.9")
        manifest["patch_sha256"] = patch_digest
        tests = ROOT / "environments/egress/gost_tests"
        test_hashes = {}
        for source, target in [("searchswe_sniffing_test.go", "internal/util/sniffing"),
                               ("searchswe_dns_test.go", "handler/dns"),
                               ("searchswe_exchanger_test.go", "resolver/exchanger")]:
            data = (tests / source).read_bytes()
            (work / "x-0.10.9" / target / source).write_bytes(data)
            test_hashes[source] = hashlib.sha256(data).hexdigest()
        env = {**os.environ, "GOTOOLCHAIN": "local", "GOMAXPROCS": "4", "CGO_ENABLED": "0",
               "GOPATH": str(cache / "gopath"), "GOCACHE": str(cache / "gocache"),
               "GOENV": "off", "GOWORK": "off", "GOFLAGS": "", "GOOS": "linux", "GOARCH": "amd64",
               "GOAMD64": "v1", "GOEXPERIMENT": "", "GO111MODULE": "on",
               "GOPRIVATE": "", "GONOPROXY": "", "GONOSUMDB": ""}
        if args.offline:
            env.update(GOPROXY="off", GOSUMDB="off")
        manifest["regression_test_sha256"] = test_hashes
        app = work / "gost-3.2.6"
        with (work / "build.log").open("w") as log:
            def run_go(*args, cwd=app):
                command([go, *args], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            for module_dir in (app, work / "x-0.10.9"):
                run_go("mod", "edit", "-go=1.26.8", "-toolchain=none",
                       *[f"-require={name}@{version}" for name, version in SECURITY_MINIMA.items()], cwd=module_dir)
            run_go("mod", "tidy", cwd=work / "x-0.10.9")
            run_go("mod", "edit", "-go=1.26.8", "-toolchain=none",
                   "-require=github.com/go-gost/x@v0.10.9", "-require=github.com/go-gost/core@v0.4.1",
                   "-replace=github.com/go-gost/x=../x-0.10.9")
            run_go("mod", "tidy")
            for filename, digest in LOCKS.items():
                if sha(app / filename) != digest:
                    raise ValueError(f"Dependency lock drift: {filename}")
            run_go("mod", "verify")
            run_go("test", "-p", "4", "./internal/util/sniffing", "./handler/dns", "./handler/redirect/tcp", "./resolver/exchanger",
                   cwd=work / "x-0.10.9")
            context = work / "image"
            context.mkdir()
            stage_archives(apk_lock, cache / "component-apks", context / "packages", download=not args.offline)
            manifest["component_apks"] = apk_lock
            (context / "Dockerfile").write_bytes(recipe_bytes)
            for name in SOURCES:
                shutil.copyfile(work / name / "LICENSE", context / f"LICENSE.{name}")
            harbor = distribution("harbor")
            if harbor.version != "0.22.0":
                raise ValueError("Base helper notice collection requires Harbor 0.22.0")
            harbor_licenses = [harbor.locate_file(file) for file in harbor.files
                               if str(file).endswith(".dist-info/licenses/LICENSE")]
            if len(harbor_licenses) != 1:
                raise ValueError("Harbor's packaged license is unavailable")
            for source, name in ((ROOT / "LICENSE", "LICENSE.Search-SWE"),
                                 (Path(harbor_licenses[0]), "LICENSE.Harbor-0.22.0")):
                shutil.copyfile(source, context / name)
            manifest["top_level_license_sha256"] = {p.name: sha(p) for p in context.glob("LICENSE.*")}
            binary = context / "gost-searchswe"
            run_go("build", "-mod=readonly", "-p", "4", "-trimpath", "-buildvcs=false", "-o", str(binary), "./cmd/gost")
            run_go("mod", "verify")
            build_info = json.loads(command([go, "version", "-m", "-json", str(binary)], env=env, capture_output=True).stdout)
            linked_paths = [build_info["Main"]["Path"], *[module["Path"] for module in build_info["Deps"]]]
            modules = list(json_stream(command([go, "list", "-m", "-json", *linked_paths], cwd=app, env=env, capture_output=True).stdout))
            goroot = command([go, "env", "GOROOT"], env=env, capture_output=True).stdout.strip()
            notices = collect_notices(build_info, modules, goroot, context / "third-party")
            manifest.update(build_info=build_info, notice_modules=len(notices["modules"]),
                            notice_index_sha256=sha(context / "third-party/index.json"))
            (context / "component-manifest.json").write_text(json.dumps({
                "binary_sha256": sha(binary), "patch_sha256": patch_digest, "sources": SOURCES, "locks": LOCKS,
                "notice_index_sha256": manifest["notice_index_sha256"],
                "top_level_license_sha256": manifest["top_level_license_sha256"],
            }))
            # BuildKit FROM does not accept Docker image IDs. Use the caller's
            # local name and verify the immutable base/layers before and after.
            if inspect(args.base_image)["Id"] != base["Id"]:
                raise ValueError("Base image changed during build")
            if sha(patcher) != patch_digest:
                raise ValueError("GOST patch source changed during build")
            if any(sha(tests / name) != digest for name, digest in test_hashes.items()):
                raise ValueError("GOST regression source changed during build")
            command(["docker", "build", "--pull=false", "--network=none", "--build-arg",
                     f"BASE_IMAGE={args.base_image}", "--build-arg", f"PATCH_SHA={patch_digest}",
                     "-t", args.tag, str(context)], stdout=log, stderr=subprocess.STDOUT, timeout=300)
        result = inspect(args.tag)
        if inspect(args.base_image)["Id"] != base["Id"] or any(sha(ROOT / p) != digest for p, digest in inputs.items()):
            raise ValueError("Base or build source changed during component build")
        final_layers = result["RootFS"]["Layers"]
        if len(final_layers) not in (1, 2):
            raise ValueError("Unexpected merged filesystem or WORKDIR layer count")
        manifest["final_layer_policy"] = "merged filesystem plus optional WORKDIR metadata layer; audit final OCI contents before release"
        manifest.update(status="built", image_id=result["Id"], binary_sha256=sha(binary), locks=LOCKS)
        print(f"Built component: {args.tag}\nImage ID: {result['Id']}\nEvidence: {work}")
    finally:
        if manifest["status"] == "building":
            manifest["status"] = "failed"
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--tag", default="searchswe-egress-component:dev1")
    parser.add_argument("--work-dir", type=Path, required=True, help="New build/evidence directory")
    parser.add_argument("--cache-dir", type=Path, required=True, help="Reusable public source/module cache")
    parser.add_argument("--offline", action="store_true", help="Require cached sources/modules; disable Go network resolution")
    build(parser.parse_args())
