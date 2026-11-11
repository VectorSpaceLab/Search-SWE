"""Trusted execution supervisor; elapsed times include process startup/exit."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
from statistics import median
import subprocess
import time

WORK = Path("/tmp/query-encoder-alignment-verifier")
LOG = Path("/logs/verifier/query-encoder-alignment-eval")
PYTHON = "/opt/conda/bin/python"
TIMEOUT = 1800


def stop_submission():
    subprocess.run(["pkill", "-KILL", "-u", "10001"], check=False)


def run_timed(command, stdout, stderr, timeout=TIMEOUT, env=None):
    """communicate uses an event wait; no Popen.wait(timeout) polling clock."""
    with Path(stdout).open("wb") as out, Path(stderr).open("wb") as err:
        started = time.monotonic()
        if env is None:
            env = {**os.environ, "OMP_NUM_THREADS": "8", "OPENBLAS_NUM_THREADS": "8"}
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err,
                                   start_new_session=True, env=env, cwd="/app")
        try:
            data, _ = process.communicate(timeout=timeout)
            elapsed = time.monotonic() - started
            out.write(data)
            status = process.returncode
            cleanup = 0.0
            try:
                os.killpg(process.pid, 0)
                background = True
            except ProcessLookupError:
                background = False
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            cleanup_start = time.monotonic()
            os.killpg(process.pid, signal.SIGKILL)
            data, _ = process.communicate()
            out.write(data)
            cleanup = time.monotonic() - cleanup_start
            status = 124
            background = False
        finally:
            # Even a normally exited parent must not leave descendants.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return {"status": status, "elapsed_seconds": elapsed, "cleanup_seconds": cleanup,
            "background_processes": background}


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(LOG, ignore_errors=True)
    WORK.mkdir(mode=0o755)
    LOG.mkdir(parents=True, mode=0o700)
    LOG.parent.chmod(0o700)
    private = WORK / "private"
    private.mkdir(mode=0o700)
    submission = Path("/app/submission")
    error = ""
    error_kind = "candidate"
    phases = {}
    starter = private / "starter.jsonl"
    baseline = private / "quality.jsonl"
    results = private / "candidate.jsonl"
    timer = {}
    samples = {"starter": [], "candidate": []}
    try:
        if not submission.is_dir() or submission.is_symlink():
            raise ValueError("submission must be a regular directory")
        if not (submission / "run.sh").is_file() or not os.access(submission / "run.sh", os.X_OK):
            raise ValueError("missing executable run.sh")
        if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in submission.rglob("*")):
            raise ValueError("submission contains a symlink or special file")
        runtime = WORK / "runtime"
        shutil.copytree(submission, runtime)
        for p in [runtime, *runtime.rglob("*")]:
            os.chown(p, 0, 0)
            p.chmod(0o555 if p.is_dir() or os.access(p, os.X_OK) else 0o444)
        for p in (Path("/tests"), Path("/audit"), Path("/logs/agent")):
            if p.exists():
                p.chmod(0o700)
        query = WORK / "queries.jsonl"
        shutil.copyfile("/tests/data/queries.jsonl", query)
        query.chmod(0o444)
        common = ["--doc-vectors", "/task/data/doc.npy", "--queries", str(query), "--top-k", "1"]
        error_kind = "infrastructure"
        quality_command = [PYTHON, "/tests/quality_reference/baseline.py", "--fit",
                           "--projection", str(private / "ridge.npz"), *common,
                           "--output", str(baseline)]
        phases["quality_baseline"] = run_timed(quality_command, LOG / "quality.stdout.log", LOG / "quality.stderr.log")
        if phases["quality_baseline"]["status"]:
            raise RuntimeError("quality baseline failed or timed out")
        for index in range(5):
            error_kind = "infrastructure"
            reference_output = private / f"starter-{index}.jsonl"
            phase = f"time-reference-{index}"
            phases[phase] = run_timed(
                ["/tests/time_reference/run.sh", *common, "--output", str(reference_output),
                 "--report", str(private / "starter-report.json")],
                LOG / f"{phase}.stdout.log", LOG / f"{phase}.stderr.log")
            if phases[phase]["status"]:
                raise RuntimeError("4B time reference failed or timed out")
            if index == 0:
                shutil.copyfile(reference_output, starter)
            elif reference_output.read_bytes() != starter.read_bytes():
                raise RuntimeError("4B time reference output is not deterministic")
            samples["starter"].append(phases[phase]["elapsed_seconds"])
            error_kind = "candidate"
            scratch = WORK / f"candidate-{index}"
            scratch.mkdir(mode=0o700)
            os.chown(scratch, 10001, 10001)
            output = scratch / "results.jsonl"
            env = {"HOME": str(scratch), "TMPDIR": str(scratch),
                   "JAVA_HOME": "/opt/java/openjdk",
                   "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/bin:/bin", "LD_LIBRARY_PATH": "/opt/conda/lib",
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HF_HUB_OFFLINE": "1",
                   "TRANSFORMERS_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "8", "OPENBLAS_NUM_THREADS": "8"}
            phase = f"candidate-{index}"
            phases[phase] = run_timed([PYTHON, "/tests/offline_exec.py", str(runtime / "run.sh"),
                                      *common, "--output", str(output)],
                                     LOG / f"{phase}.stdout.log", LOG / f"{phase}.stderr.log", env=env)
            remaining = subprocess.run(["pgrep", "-u", "10001"], capture_output=True).returncode == 0
            stop_submission()
            if phases[phase]["status"]:
                raise ValueError(f"{phase} exited with status {phases[phase]['status']}")
            if remaining or phases[phase]["background_processes"]:
                raise ValueError("candidate left background processes")
            if not output.is_file() or output.is_symlink():
                raise ValueError("candidate did not produce a regular output file")
            if index == 0:
                shutil.copyfile(output, results)
            elif output.read_bytes() != results.read_bytes():
                raise ValueError("candidate output is not deterministic")
            samples["candidate"].append(phases[phase]["elapsed_seconds"])
            shutil.rmtree(scratch)
        timer = {name: median(values) for name, values in samples.items()}
    except Exception as exc:
        error = str(exc)
    finally:
        stop_submission()
    (LOG / "phases.json").write_text(json.dumps(phases, indent=2) + "\n")
    (LOG / "timing-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    for name, seconds in timer.items():
        (private / f"{name}-time.txt").write_text(str(seconds))
    # Preserve raw predictions and fitted-parameter provenance in protected logs.
    for name in ("starter.jsonl", "quality.jsonl", "candidate.jsonl", "ridge.json"):
        if (private / name).exists():
            shutil.copyfile(private / name, LOG / name)
    env = {**os.environ,
           "SEARCH_SWE_STARTER_OUTPUT": str(starter), "SEARCH_SWE_CANDIDATE_OUTPUT": str(results),
           "SEARCH_SWE_QUALITY_OUTPUT": str(baseline),
           "SEARCH_SWE_STARTER_REPORT": str(private / "starter-report.json"),
           "SEARCH_SWE_STARTER_TIME_FILE": str(private / "starter-time.txt"),
           "SEARCH_SWE_CANDIDATE_TIME_FILE": str(private / "candidate-time.txt"),
           "SEARCH_SWE_EXECUTION_ERROR": error, "SEARCH_SWE_ERROR_KIND": error_kind}
    return subprocess.run([PYTHON, "/tests/grader.py"], env=env).returncode


if __name__ == "__main__":
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(main())
