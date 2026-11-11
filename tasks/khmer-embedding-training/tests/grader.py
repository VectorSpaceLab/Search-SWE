#!/usr/bin/env python3
"""Rebuild the submitted index before applying root-only retrieval labels."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "evaluation"))
from checkpoint import file_hash, validate_checkpoint
from metrics import read_jsonl, score_results
from score_mapping import normalize_score

LOG = Path("/logs/verifier/khmer-embedding-training-eval")
CORPUS = Path("/task/data/corpus.parquet")
BACKBONE = Path("/task/models/multilingual-e5-large")
PRIVATE = Path("/tests/data")
APP = Path("/app")
CONTRACT = json.loads(Path(__file__).with_name("runtime_contract.json").read_text())


class SubmissionError(Exception):
    pass


def write_report(report):
    LOG.mkdir(parents=True, exist_ok=True)
    (LOG / "evaluation.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )


def fingerprint():
    root = Path(__file__).resolve().parent / "evaluation"
    return {
        name: file_hash(path)
        for name, path in {
            "corpus": CORPUS,
            "queries": PRIVATE / "queries.jsonl",
            "answers": PRIVATE / "answers.jsonl",
            "backbone": BACKBONE / "model.safetensors",
            "evaluator": root / "evaluator.py",
            "metrics": root / "metrics.py",
            "checkpoint_validator": root / "checkpoint.py",
        }.items()
    }


def kill_user(user):
    for sig in ("-TERM", "-KILL"):
        subprocess.run(
            ["pkill", sig, "-u", user],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def stage_directory(path, user):
    info = pwd.getpwnam(user)
    path.mkdir(parents=True, exist_ok=False)
    os.chown(path, info.pw_uid, info.pw_gid)
    path.chmod(0o700)
    (path / "tmp").mkdir(mode=0o700)
    os.chown(path / "tmp", info.pw_uid, info.pw_gid)


def run_stage(user, argv, work, log, timeout):
    env = {
        "HOME": str(work),
        "USER": user,
        "JAVA_HOME": "/opt/java/openjdk",
        "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "TMPDIR": str(work / "tmp"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "LD_LIBRARY_PATH": "/usr/local/nvidia/lib:/usr/local/nvidia/lib64",
    }
    command = [
        "/usr/sbin/runuser",
        "-u",
        user,
        "--",
        "/opt/conda/bin/python",
        "-I",
        "/opt/task-runtime/offline_exec.py",
        *map(str, argv),
    ]
    started = time.monotonic()
    try:
        with (
            log.with_suffix(".stdout.log").open("w") as out,
            log.with_suffix(".stderr.log").open("w") as err,
        ):
            completed = subprocess.run(
                command, env=env, cwd=work, stdout=out, stderr=err,
                stdin=subprocess.DEVNULL, close_fds=True, timeout=timeout
            )
        if completed.returncode:
            raise SubmissionError(
                f"{log.name} exited with status {completed.returncode}"
            )
    except subprocess.TimeoutExpired as exc:
        raise SubmissionError(f"{log.name} exceeded its execution budget") from exc
    finally:
        kill_user(user)
    return time.monotonic() - started


def seal_index(index):
    if index.is_symlink() or not index.is_dir():
        raise SubmissionError("build.sh did not create the requested index")
    paths = [index, *index.rglob("*")]
    if not any(p.is_file() for p in paths):
        raise SubmissionError("build.sh produced an empty index")
    gid = pwd.getpwnam("submission").pw_gid
    for p in paths:
        mode = p.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise SubmissionError("Index entries must be regular files or directories")
        os.chown(p, 0, gid)
        p.chmod(0o550 if stat.S_ISDIR(mode) else 0o440)


def run_pipeline(app, corpus, queries, root, log, contract):
    """Build once without queries, then run twice against that new index."""
    root.chmod(0o711)
    log.mkdir(parents=True, exist_ok=True)
    for script in ("build.sh", "run.sh"):
        p = app / script
        if p.is_symlink() or not p.is_file() or not os.access(p, os.X_OK):
            raise SubmissionError(f"Missing executable {script}")
    build_work = root / "build"
    stage_directory(build_work, "submission")
    index = build_work / "index"
    if index.exists():
        raise RuntimeError("Verifier index directory must start absent")
    report = {
        "index_initially_absent": True,
        "build_invocations": 0,
        "run_invocations": 0,
    }
    report["build_seconds"] = run_stage(
        "submission",
        [app / "build.sh", "--corpus", corpus, "--index-dir", index],
        build_work,
        log / "build",
        contract["build_timeout_sec"],
    )
    report["build_invocations"] = 1
    seal_index(index)
    # No build scratch files are exposed to the retrieval user.
    for p in build_work.iterdir():
        if p != index:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
    os.chown(build_work, 0, 0)
    build_work.chmod(0o711)
    report["index_read_only"] = True
    # Query inputs are first created only after the builder has exited.
    results = []
    batches = contract["query_batches"]
    for batch in range(batches):
        start, end = (
            len(queries) * batch // batches,
            len(queries) * (batch + 1) // batches,
        )
        selected = queries[start:end]
        if not selected:
            continue
        work = root / f"run-{batch}"
        stage_directory(work, "retrieval")
        query_file = work / "queries.jsonl"
        query_file.write_text(
            "".join(
                json.dumps(
                    {"id": q["id"], "question": q["question"]}, ensure_ascii=False
                )
                + "\n"
                for q in selected
            )
        )
        os.chown(query_file, 0, pwd.getpwnam("submission").pw_gid)
        query_file.chmod(0o440)
        output = work / "results.jsonl"
        seconds = run_stage(
            "retrieval",
            [
                app / "run.sh",
                "--index-dir",
                index,
                "--queries",
                query_file,
                "--output",
                output,
            ],
            work,
            log / f"run-{batch}",
            contract["run_timeout_sec"],
        )
        report[f"run_{batch}_seconds"] = seconds
        report["run_invocations"] += 1
        if output.is_symlink() or not output.is_file():
            raise SubmissionError("run.sh did not create the requested result file")
        try:
            rows = read_jsonl(output)
        except (OSError, ValueError) as exc:
            raise SubmissionError("Invalid retrieval JSONL") from exc
        if len(rows) != len(selected) or any(
            not isinstance(row, dict) or row.get("id") != q["id"]
            for q, row in zip(selected, rows)
        ):
            raise SubmissionError("Query coverage or order mismatch")
        results.extend(rows)
        os.chown(work, 0, 0)
        work.chmod(0o700)
    (log / "pipeline.json").write_text(json.dumps(report, indent=2) + "\n")
    return results, report


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((PRIVATE / "baseline.json").read_text())
    expected = fingerprint()
    if (
        baseline.get("fingerprint") != expected
        or baseline.get("corpus_count") != 2681468
        or baseline.get("query_count") != 1000
    ):
        raise RuntimeError("Bundled baseline is stale")
    if not baseline.get("valid") or not 0 <= baseline["recall@100"] < 1:
        raise RuntimeError("Invalid measured baseline")
    queries, answers = read_jsonl(PRIVATE / "queries.jsonl"), read_jsonl(
        PRIVATE / "answers.jsonl"
    )
    try:
        if os.environ.get("SEARCH_SWE_EXECUTION_ERROR"):
            raise SubmissionError(os.environ["SEARCH_SWE_EXECUTION_ERROR"])
        try:
            validate_checkpoint(APP / "submission/model", BACKBONE)
        except (OSError, ValueError, KeyError) as exc:
            raise SubmissionError("Invalid embedding checkpoint: " + str(exc)) from exc
        root = Path(tempfile.mkdtemp(prefix="khmer-eval-", dir="/run"))
        root.chmod(0o711)
        checkpoint_work = root / "checkpoint"
        stage_directory(checkpoint_work, "submission")
        checkpoint_seconds = run_stage(
            "submission",
            [
                "/opt/conda/bin/python", "-I",
                "/opt/task-runtime/check_checkpoint.py", "--load-standard",
                APP / "submission/model",
            ],
            checkpoint_work, LOG / "checkpoint-load", CONTRACT["checkpoint_timeout_sec"],
        )
        results, pipeline = run_pipeline(APP, CORPUS, queries, root, LOG, CONTRACT)
        try:
            result = score_results(CORPUS, queries, answers, results)
        except (ValueError, TypeError, KeyError) as exc:
            raise SubmissionError("Invalid retrieval output: " + str(exc)) from exc
        result["checkpoint_load_seconds"] = checkpoint_seconds
        result["pipeline"] = pipeline
        result["executable_gate"] = True
        result["baseline_recall@20"] = baseline["recall@20"]
        result["baseline_recall@100"] = baseline["recall@100"]
        result["reward"] = normalize_score(result["recall@100"])
    except SubmissionError as exc:
        # A broken submission is a valid zero; infrastructure failures remain invalid.
        result = {
            "valid": True,
            "executable_gate": False,
            "reward": 0.0,
            "error": str(exc),
        }
    write_report(result)
    print(json.dumps({k: v for k, v in result.items() if k != "per_query"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        write_report(
            {
                "valid": False,
                "reward": 0.0,
                "error": type(exc).__name__ + ": " + str(exc),
            }
        )
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
