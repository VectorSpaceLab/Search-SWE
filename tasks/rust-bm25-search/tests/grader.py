#!/usr/bin/env python3
"""Recompile Rust, rebuild its index, and compare against a local Pyserini run."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from benchmark import index_bytes, measure, sha256
from evaluate import InvalidSubmission, evaluate, load_qrels, load_queries, quality_passes, tradeoff_reward
from prepare_corpus import CORPUS_DOCUMENTS, prepare

TESTS = Path(__file__).resolve().parent
WORK = Path("/work")
LOG = Path("/logs/verifier")
UID = 10001
THREADS = 4
GIB = 1024**3
WEIGHTS = {"quality": 1.0, "time": 1.0, "disk": 1.0}
ENV = {"PATH": "/opt/rust/bin:/usr/bin:/bin", "HOME": "/work/tmp", "TMPDIR": "/work/tmp",
       "CARGO_HOME": "/work/cargo", "CARGO_TARGET_DIR": "/work/target",
       "RAYON_NUM_THREADS": "4", "OMP_NUM_THREADS": "4", "LC_ALL": "C.UTF-8"}


def kill_submission_processes():
    """This UID belongs exclusively to this disposable verifier container."""
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                if entry.stat().st_uid == UID:
                    os.kill(int(entry.name), signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass


def tree_bytes(path: Path, *, limit: int = 64 * GIB) -> int:
    total, count = 0, 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(root) / name
            try:
                info = item.lstat()
            except FileNotFoundError:
                # Compilers legitimately rename/remove temporary files while
                # the monitor walks the workspace. A removed file uses no space.
                continue
            if stat.S_ISLNK(info.st_mode):
                continue  # Never follow a candidate link during quota monitoring.
            count += 1
            total += info.st_size if stat.S_ISREG(info.st_mode) else 0
            if total > limit or count > 100_000:
                raise InvalidSubmission("Workspace exceeds 64 GiB or 100,000 entries")
    return total


def run_candidate(mode: str, command: list[str], *, timeout: int, cwd: Path) -> float:
    started = time.monotonic()
    with (LOG / f"{mode}.stderr.log").open("wb") as output:
        process = subprocess.Popen([sys.executable, str(TESTS / "isolate.py"), mode, *command],
                                   cwd=cwd, env=ENV, stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise InvalidSubmission(f"{mode} exceeded {timeout} seconds")
                if tree_bytes(WORK) + tree_bytes(LOG) > 64 * GIB:
                    raise InvalidSubmission("Workspace and logs exceed 64 GiB")
                time.sleep(.5)
            if process.returncode:
                raise InvalidSubmission(f"{mode} exited with status {process.returncode}")
        finally:
            kill_submission_processes()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    return time.monotonic() - started


def own_tree(directory: Path, uid: int, *, readonly=False):
    for root, dirs, files in os.walk(directory, followlinks=False):
        for path in [Path(root), *[Path(root) / name for name in files]]:
            if path.is_symlink():
                raise InvalidSubmission("Unexpected symlink")
            os.chown(path, uid, uid)
            os.chmod(path, (0o555 if path.is_dir() else 0o444) if readonly
                     else (0o755 if path.is_dir() else 0o644))


def copy_source(source: Path):
    if source.is_symlink() or not source.is_dir():
        raise InvalidSubmission("Missing /app/submission source directory")
    paths, total = [], 0
    for path in source.rglob("*"):
        info = path.lstat()
        rel = path.relative_to(source)
        if stat.S_ISDIR(info.st_mode):
            if len(rel.parts) > 10:
                raise InvalidSubmission("Source tree is too deeply nested")
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InvalidSubmission("Submission may contain only ordinary source files")
        allowed = str(rel) in {"Cargo.toml", "Cargo.lock", "README.md"} or (
            rel.parts[0] == "src" and path.suffix == ".rs")
        if not allowed:
            raise InvalidSubmission(f"Unexpected submission file: {rel}; remove build outputs and data")
        total += info.st_size
        paths.append((path, rel))
        if total > 10 * 1024**2 or len(paths) > 1000:
            raise InvalidSubmission("Source exceeds 10 MiB or 1,000 files")
    manifest = tomllib.loads((source / "Cargo.toml").read_text())
    package = manifest.get("package")
    if not isinstance(package, dict) or package.get("name") != "bm25-search":
        raise InvalidSubmission("Cargo package must be named bm25-search")
    if package.get("build") or any(key in manifest for key in
            ["build-dependencies", "workspace", "patch", "replace"]):
        raise InvalidSubmission("Custom build scripts, workspaces, patches and vendored dependencies are excluded")
    if not (source / "Cargo.lock").is_file() or not (source / "src/main.rs").is_file():
        raise InvalidSubmission("Cargo.lock and src/main.rs are required")
    target = WORK / "source"
    target.mkdir()
    for path, rel in paths:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    own_tree(target, UID)


def build_submission():
    copy_source(Path("/app/submission"))
    shutil.copytree("/opt/cargo", WORK / "cargo")
    own_tree(WORK / "cargo", UID)
    for name in ["target", "tmp", "index"]:
        path = WORK / name
        path.mkdir()
        os.chown(path, UID, UID)
    compile_seconds = run_candidate("compile", ["cargo", "build", "--release", "--offline",
                                    "--locked", "--bin", "bm25-search", "-j", str(THREADS)],
                                    timeout=600, cwd=WORK / "source")
    built = WORK / "target/release/bm25-search"
    if built.is_symlink() or not built.is_file() or built.stat().st_size > 100 * 1024**2:
        raise InvalidSubmission("Missing or oversized compiled binary")
    executable = WORK / "bm25-search"
    shutil.copyfile(built, executable)
    os.chmod(executable, 0o555)
    # Do not leave source, dependency caches, or compiler outputs accessible to
    # index/search. Landlock also restricts each launched process independently.
    for path in [WORK / "source", WORK / "cargo", WORK / "target"]:
        os.chown(path, 0, 0)
        os.chmod(path, 0o700)
    index_seconds = run_candidate("index", [str(executable), "index", "--corpus",
                                  "/task/data/corpus.jsonl.gz", "--index", "/work/index",
                                  "--threads", str(THREADS)], timeout=7200, cwd=WORK)
    disk = index_bytes(WORK / "index")
    if disk > 16 * GIB:
        raise InvalidSubmission("Index exceeds 16 GiB")
    own_tree(WORK / "index", 0, readonly=True)
    shutil.rmtree(WORK / "tmp")
    (WORK / "tmp").mkdir(mode=0o700)
    return {"compile_seconds": compile_seconds, "build_seconds": index_seconds, "index_bytes": disk}


def reference_run():
    reference = WORK / "reference"
    reference.mkdir(mode=0o700)
    collection, index = reference / "collection", reference / "index"
    prepare(Path("/task/data/corpus.jsonl.gz"), collection)
    common_env = {**os.environ, "JAVA_TOOL_OPTIONS": "-Xmx10g -XX:ActiveProcessorCount=4"}
    commands = [
        ["build", "--collection", str(collection), "--index", str(index), "--threads", "4"],
        ["measure", "--index", str(index), "--queries", str(TESTS / "data/dev.queries.jsonl"),
         "--qrels", str(TESTS / "data/dev.qrels.tsv"), "--warmup", "/task/data/warmup.jsonl.gz",
         "--output", str(LOG / "reference")],
    ]
    for args in commands:
        with (LOG / f"reference-{args[0]}.log").open("wb") as stream:
            subprocess.run([sys.executable, str(TESTS / "reference.py"), *args], env=common_env,
                           stdout=stream, stderr=subprocess.STDOUT, timeout=7500 if args[0] == "build" else 37200, check=True)
    result = json.loads((LOG / "reference/reference.json").read_text())
    # Validate the exact quality floor independently of the current timing run.
    pinned = json.loads((TESTS / "reference-quality.json").read_text())
    if result["quality"] != pinned["quality"]:
        raise RuntimeError("Reference quality drifted from the checked-in measurement")
    return result


def main():
    if os.geteuid() != 0 or not Path("/.dockerenv").exists():
        raise RuntimeError("Run only in a disposable verifier container as root")
    LOG.mkdir(parents=True, exist_ok=True)
    os.chmod(LOG, 0o700)
    (LOG / "reward.txt").write_text("0\n")
    WORK.mkdir(mode=0o711, exist_ok=False)
    # Candidate scratch is /work/tmp. Other ordinary writable scratch paths
    # must not bypass workspace accounting in this disposable container.
    for name in ["/tmp", "/var/tmp", "/run/lock", "/home/submission"]:
        path = Path(name)
        if path.is_dir():
            os.chown(path, 0, 0)
            os.chmod(path, 0o700)
    report = {"status": "running", "reward": 0.0, "weights": WEIGHTS}
    try:
        # A missing kernel feature is an infrastructure error, not model failure.
        import ctypes
        abi = ctypes.CDLL(None, use_errno=True).syscall(444, 0, 0, 1)
        if abi < 1:
            raise RuntimeError("Verifier requires Linux Landlock ABI >= 1")
        # Exercise the same unprivileged launcher before considering a source
        # submission. A missing seccomp facility must invalidate the run.
        subprocess.run([sys.executable, str(TESTS / "isolate.py"), "compile", "/bin/true"],
                       cwd=WORK, env=ENV, check=True, timeout=10, capture_output=True)
        pinned = json.loads((TESTS / "reference-quality.json").read_text())
        for name, key in [("corpus.jsonl.gz", "corpus_sha256"), ("warmup.jsonl.gz", "warmup_sha256")]:
            if sha256(Path("/task/data") / name) != pinned["inputs"][key]:
                raise RuntimeError(f"Fixed input checksum mismatch: {name}")
        try:
            report.update(build_submission())
        except (OSError, ValueError) as error:
            raise InvalidSubmission(str(error)) from error
        queries = load_queries(TESTS / "data/dev.queries.jsonl")
        warmup = load_queries(Path("/task/data/warmup.jsonl.gz"))
        qrels = load_qrels(TESTS / "data/dev.qrels.tsv", {q["query_id"] for q in queries})
        metrics, rows = measure([sys.executable, str(TESTS / "isolate.py"), "search",
                                 "/work/bm25-search", "search", "--index", "/work/index",
                                 "--threads", str(THREADS)], queries=queries, warmup=warmup,
                                directory=LOG / "candidate", document_count=CORPUS_DOCUMENTS,
                                cwd=WORK, env=ENV, cleanup=kill_submission_processes)
        report.update(metrics)
        report["quality"] = evaluate(rows, queries, qrels, document_count=CORPUS_DOCUMENTS)
        report["reference"] = reference_run()
        report["quality_pass"] = quality_passes(report["quality"], report["reference"]["quality"])
        report["reward"] = tradeoff_reward(report, report["reference"], WEIGHTS)
        report["status"] = "ok" if report["quality_pass"] else "quality_below_reference"
        (LOG / "reward.txt").write_text(f"{report['reward']:.12f}\n")
    except (InvalidSubmission, TimeoutError) as error:
        report.update(status="invalid_submission", error=str(error))
    except Exception as error:
        report.update(status="infrastructure_or_contract_error", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        kill_submission_processes()
        (LOG / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps({k: report[k] for k in ["status", "reward"]}))


if __name__ == "__main__":
    main()
