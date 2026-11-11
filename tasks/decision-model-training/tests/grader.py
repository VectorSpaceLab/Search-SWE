"""Run a submission with hidden data isolated and an aggregate inference clock."""
from collections import Counter
import json
import os
from pathlib import Path
import random
import secrets
import shutil
import signal
import stat
import subprocess
import time

from scoring import VerificationError, strict_json, score_predictions

PRIVATE = Path("/tests/data")
SUBMISSION = Path("/app/submission")
LOGS = Path("/logs/verifier")
WORK = Path("/tmp/decision-eval")
UID = GID = 10001
STARTUP_SECONDS = 120
INFERENCE_SECONDS = 240
DATASETS = {"ag_news", "banking77", "civil_comments_toxicity", "clinc_oos",
            "helpsteer_helpfulness", "massive_intent", "sst5"}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def read_rows(path):
    with path.open() as stream:
        return [strict_json(line) for line in stream if line.strip()]


def stop_children():
    for sig in ("TERM", "KILL"):
        subprocess.run(["/usr/bin/pkill", "-" + sig, "-u", str(UID)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if sig == "TERM":
            time.sleep(.1)


def child_command(command, runtime):
    environment = {"JAVA_HOME": "/opt/java/openjdk",
                   "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
        "USER": "submission", "LOGNAME": "submission", "HOME": str(runtime),
        "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "16", "MKL_NUM_THREADS": "16", "OPENBLAS_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false", "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1", "TMPDIR": str(runtime / "tmp"),
        "XDG_CACHE_HOME": str(runtime / "cache"), "HF_HOME": str(runtime / "cache/huggingface"),
        "TORCH_HOME": str(runtime / "cache/torch")}
    for name in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES", "LD_LIBRARY_PATH"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    return ["/usr/sbin/runuser", "-u", "submission", "--", "/usr/bin/setpriv",
            "--no-new-privs", "/usr/bin/env", "-i",
            *[f"{k}={v}" for k, v in environment.items()], *command]


def run_timed(command, runtime, seconds, phase, started=None):
    started = time.monotonic() if started is None else started
    with (LOGS / f"{phase}.stdout.log").open("wb") as stdout, (LOGS / f"{phase}.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(child_command(command, runtime), cwd=SUBMISSION,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        timed_out = False
        try:
            status = process.wait(timeout=max(0, seconds - (time.monotonic() - started)))
            elapsed = time.monotonic() - started
            timed_out = elapsed > seconds
        except subprocess.TimeoutExpired:
            elapsed, timed_out, status = time.monotonic() - started, True, None
        if timed_out:
            stop_children()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        return {"elapsed_seconds": elapsed, "returncode": status, "timed_out": timed_out}


def prepare_workspace():
    # The test supervisor makes /tmp root-owned/non-writable before any child.
    if WORK.exists():
        if WORK.is_symlink() or not WORK.is_dir():
            WORK.unlink()
        else:
            shutil.rmtree(WORK)
    WORK.mkdir(mode=0o711)
    runtime = WORK / ("runtime-" + secrets.token_hex(8))
    output = WORK / ("output-" + secrets.token_hex(8))
    inputs = WORK / ("input-" + secrets.token_hex(8))
    for path in (runtime, output):
        path.mkdir(mode=0o700)
        os.chown(path, UID, GID)
    for name in ("tmp", "cache"):
        (runtime / name).mkdir(mode=0o700)
        os.chown(runtime / name, UID, GID)
    inputs.mkdir(mode=0o700)  # Inaccessible to submitted code until the clock starts.
    return runtime, inputs, output


def check_boundary(runtime):
    checks = ["test -x /app/submission/start.sh", "test -x /app/submission/run.sh",
              "test ! -w /app/submission", "test ! -r /task/data/examples.jsonl",
              "test -r /task/models/Qwen3-0.6B/model.safetensors",
              "test ! -r /tests/grader.py", "test ! -r /tests/data/answers.jsonl",
              "test ! -r /tests/data/requests.jsonl", "test ! -w /logs/verifier",
              'test -z "${OPENAI_API_KEY+x}"', 'test -z "${CODEX_HOME+x}"']
    result = subprocess.run(child_command(["/bin/sh", "-c", " && ".join(checks)], runtime),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    if result.returncode:
        raise VerificationError("Submission isolation or required-file check failed")


def read_output(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise VerificationError("Output must be a regular JSONL file")
        with os.fdopen(fd, "r", closefd=False) as stream:
            return [strict_json(line) for line in stream if line.strip()]
    finally:
        os.close(fd)


def evaluate(report):
    requests, references = read_rows(PRIVATE / "requests.jsonl"), read_rows(PRIVATE / "answers.jsonl")
    counts = Counter(r["dataset"] for r in references)
    if len(requests) != 4200 or set(counts) != DATASETS or set(counts.values()) != {600}:
        raise VerificationError("The full seven-dataset suite is required")
    if any(len(r["questions"]) != 1 for r in requests):
        raise VerificationError("Unexpected reference schema")
    # Validate all gold/coverage before launching untrusted code.
    score_predictions(requests, references,
                      [{"request_id": r["request_id"], "answers": r["answers"]} for r in references])
    runtime, inputs, output = prepare_workspace()
    check_boundary(runtime)
    report["startup"] = run_timed([str(SUBMISSION / "start.sh"), "--runtime-dir", str(runtime)],
                                  runtime, STARTUP_SECONDS, "startup")
    if report["startup"]["timed_out"] or report["startup"]["returncode"] != 0:
        raise VerificationError("Startup failed or exceeded 120 seconds")

    original = {r["request_id"]: r for r in references}
    private_gold, runtime_requests = [], []
    # Keep schema groups together for a stable workload; shuffle rows within
    # each group and assign fresh IDs. No original IDs or gold enter the child.
    for dataset in sorted(DATASETS):
        group = [r for r in requests if original[r["request_id"]]["dataset"] == dataset]
        random.SystemRandom().shuffle(group)
        for row in group:
            rid = secrets.token_hex(16)
            runtime_requests.append({"request_id": rid, "state": row["state"], "questions": row["questions"]})
            private_gold.append({**original[row["request_id"]], "request_id": rid})
    request_path, output_path = inputs / "requests.jsonl", output / "results.jsonl"
    with request_path.open("w") as stream:
        for row in runtime_requests:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    os.chown(request_path, 0, GID)
    request_path.chmod(0o440)
    os.chown(inputs, 0, GID)
    started = time.monotonic()
    inputs.chmod(0o750)  # First moment the submission can access hidden requests.
    report["inference"] = run_timed([str(SUBMISSION / "run.sh"), "--runtime-dir", str(runtime),
        "--requests", str(request_path), "--output", str(output_path)],
        runtime, INFERENCE_SECONDS, "inference", started=started)
    stop_children()  # Snapshot completed output only after all writers have stopped.
    if report["inference"]["timed_out"] or report["inference"]["returncode"] != 0:
        raise VerificationError("Inference failed or exceeded 240 seconds")
    metrics = score_predictions(runtime_requests, private_gold, read_output(output_path))
    report.update(metrics)
    report.update({"valid": True, "reward": metrics["accuracy"]})


def main():
    if os.getuid() != 0 or not Path("/.dockerenv").exists():
        raise RuntimeError("Run only inside a disposable verifier container")
    report = {"valid": False, "reward": 0.0}
    try:
        evaluate(report)
    except Exception as error:
        report.update({"valid": False, "reward": 0.0, "error": f"{type(error).__name__}: {error}"})
    finally:
        stop_children()
    write_json(LOGS / "evaluation.json", report)
    write_json(LOGS / "reward.json", {"accuracy": report.get("accuracy", 0.0), "reward": report["reward"]})
    (LOGS / "reward.txt").write_text(f"{report['reward']:.17g}\n")
    print(json.dumps(report, allow_nan=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
