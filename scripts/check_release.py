#!/usr/bin/env python3
"""Check release files and asset mappings without starting containers or downloading."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from download_assets import REPO, matches, read_manifest, relative_path


def check_release(repo, hf_data=None, verify_data=False, allow_unpublished=False):
    errors, warnings = [], []
    pending_tasks = set()
    if allow_unpublished and hf_data is None:
        errors.append("Unpublished asset checks require a local HF staging directory.")
    license_path = repo / "LICENSE"
    if not license_path.is_file() or not license_path.read_text().strip():
        warnings.append("Code license is unspecified; choose it before an open-source release.")

    tasks = sorted(path for path in (repo / "tasks").iterdir() if path.is_dir())
    if not tasks:
        errors.append("No task packages found.")
    runtime_paths, dataset_files = [], {}
    required = (
        "instruction.md", "task.toml", "assets.json", "environment/Dockerfile",
        "environment/docker-compose.yaml", "tests/Dockerfile",
        "tests/docker-compose.yaml", "tests/test.sh",
    )
    for task in tasks:
        for name in required:
            path = task / name
            if not path.is_file() or not path.stat().st_size:
                errors.append(f"{task.name}: missing or empty {name}")
        try:
            config = tomllib.loads((task / "task.toml").read_text())
            if not config.get("task", {}).get("version"):
                errors.append(f"{task.name}: missing task version")
            manifest = read_manifest(task)
            for entry in manifest["files"]:
                runtime_paths.append(f"tasks/{task.name}/{entry['path']}")
                source = entry.get("source", {})
                if "local_path" in source:
                    local = task / relative_path(source["local_path"])
                    if not local.resolve().is_relative_to(task.resolve()) or not matches(local, entry):
                        errors.append(f"{task.name}/{entry['path']}: invalid bundled metadata")
                    continue
                if not re.fullmatch(r"[0-9a-f]{40}", source.get("revision") or ""):
                    if (allow_unpublished and hf_data is not None and source.get("revision") is None
                            and source.get("repo_type") == "dataset" and source.get("repo_id") == "search-swe/Search-SWE"):
                        pending_tasks.add(task.name)
                    else:
                        errors.append(f"{task.name}/{entry['path']}: source revision is not an immutable commit")
                if not source.get("repo_id") or source.get("repo_type") not in ("dataset", "model"):
                    errors.append(f"{task.name}/{entry['path']}: invalid source repository")
                relative_path(source["filename"])
                if source.get("repo_type") == "dataset" and source.get("repo_id") == "search-swe/Search-SWE":
                    name = source["filename"]
                    if name in dataset_files and dataset_files[name] != (entry["size_bytes"], entry["sha256"]):
                        errors.append(f"Conflicting asset references: {name}")
                    dataset_files[name] = (entry["size_bytes"], entry["sha256"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"{task.name}: {error}")

    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=repo, check=True, capture_output=True, text=True,
        )
        candidates = sorted(set(filter(None, result.stdout.split("\0"))))
        secret = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
        for name in candidates:
            path = repo / name
            if not path.is_file():
                continue  # A tracked deletion is absent from the next commit.
            if name in runtime_paths:
                errors.append(f"Downloaded runtime asset would enter Git: {name}")
            if path.stat().st_size >= 100 * 1024**2:
                errors.append(f"Git file is at least 100 MiB: {name}")
                continue
            if path.name.startswith(".env") and path.name != ".env.example":
                errors.append(f"Local environment file would enter Git: {name}")
            try:
                text = path.read_text()
            except UnicodeError:
                continue
            if secret.search(text):
                errors.append(f"Possible credential in Git file: {name} (value omitted)")
        if runtime_paths:
            ignored = subprocess.run(
                ["git", "check-ignore", "--no-index", "--stdin"], cwd=repo,
                input="\n".join(runtime_paths) + "\n", capture_output=True, text=True,
            )
            if ignored.returncode not in (0, 1):
                errors.append("Could not verify Git ignore rules.")
            for name in sorted(set(runtime_paths) - set(ignored.stdout.splitlines())):
                errors.append(f"Runtime asset is not ignored by Git: {name}")
    except (OSError, subprocess.CalledProcessError):
        errors.append("Git file checks require a Git checkout and the git executable.")

    if hf_data is not None:
        for name in ("README.md", "SOURCES.md", "manifest.json", ".gitattributes"):
            if not (hf_data / name).is_file() or not (hf_data / name).stat().st_size:
                errors.append(f"HF staging: missing or empty {name}")
        try:
            manifest = json.loads((hf_data / "manifest.json").read_text())
            if manifest.get("schema_version") != 1:
                raise ValueError("unsupported manifest schema")
            listed = set()
            for entry in manifest["files"]:
                name = entry["path"]
                rel = relative_path(name)
                path = hf_data / rel
                if name in listed:
                    errors.append(f"HF staging: duplicate manifest path {name}")
                listed.add(name)
                if not path.resolve().is_relative_to(hf_data.resolve()):
                    errors.append(f"HF staging: path leaves the dataset directory: {name}")
                    continue
                if dataset_files.get(name) != (entry["size_bytes"], entry["sha256"]):
                    errors.append(f"HF staging: no matching task asset for {name}")
                if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
                    errors.append(f"HF staging: missing or incorrect size: {name}")
                elif verify_data and not matches(path, entry):
                    errors.append(f"HF staging: SHA-256 mismatch: {name}")
            actual = {
                path.relative_to(hf_data).as_posix()
                for path in (hf_data / "tasks").rglob("*") if path.is_file()
            }
            for name in sorted(actual - listed):
                errors.append(f"HF staging: unlisted task file {name}")
            for name in sorted(dataset_files.keys() - listed):
                errors.append(f"HF staging: task asset missing from manifest: {name}")
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"HF staging: {error}")
    for name in sorted(pending_tasks):
        warnings.append(f"{name}: local dataset assets are staged; publish them and pin the HF commit before remote downloads.")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-data", type=Path, help="Optional local Hugging Face staging directory")
    parser.add_argument("--verify-data", action="store_true", help="Also hash every HF data file")
    parser.add_argument("--allow-unpublished", action="store_true", help="Check local staging with unpinned new dataset assets; requires --hf-data")
    args = parser.parse_args()
    if args.verify_data and args.hf_data is None:
        parser.error("--verify-data requires --hf-data")
    if args.allow_unpublished and args.hf_data is None:
        parser.error("--allow-unpublished requires --hf-data")
    errors, warnings = check_release(REPO, args.hf_data, args.verify_data, args.allow_unpublished)
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    print(f"Static package check: {len(errors)} errors, {len(warnings)} warnings.")
    print("Container builds, runtime API access, and license review are separate checks.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
