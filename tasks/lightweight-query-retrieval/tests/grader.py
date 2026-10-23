#!/usr/bin/env python3
"""Protected, offline verifier for a persistent batch retrieval service."""
import json
import os
from pathlib import Path
import random
import secrets
import selectors
import shutil
import signal
import stat
import statistics
import subprocess
import time

from scoring import VerificationError, strict_json, validate_response, quality, speed_reward

TASK = "lightweight-query-retrieval"
PRIVATE = Path("/tests/data")
PUBLIC = Path("/task/data")
WORK = Path("/tmp/lightweight-query-retrieval-eval")
INDEX = WORK / "index"
LOGS = Path("/logs/verifier")
UID = GID = 10001
BUILD_SECONDS = 1200
LOAD_SECONDS = 120
WARMUP_SECONDS = 60
QUERY_SECONDS = 120
REPEATS = 3
CORPUS_COUNT = 66454
QUERY_COUNT = 1271

# User-approved linear scoring; full credit is a theoretical zero-second limit.
MINIMUM_QUALITY = 0.45
FAST_SECONDS = 0.0
SLOW_SECONDS = 0.8


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n")


def read_rows(path):
    return [strict_json(line) for line in path.open() if line.strip()]


def stop_children():
    for name in ("TERM", "KILL"):
        subprocess.run(["/usr/bin/pkill", "-"+name, "-u", str(UID)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if name == "TERM":
            time.sleep(.1)
    # System V IPC survives its creating process and is not under TMPDIR.
    # Remove the submission user's IPC objects between fresh timed instances.
    subprocess.run(["/usr/sbin/runuser", "-u", "submission", "--", "/usr/bin/ipcrm", "--all"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=True)


def command(arguments, scratch):
    env = ["PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "USER=submission", "LOGNAME=submission",
        f"HOME={scratch}", f"TMPDIR={scratch}", f"XDG_CACHE_HOME={scratch / 'cache'}",
        f"HF_HOME={scratch / 'huggingface'}", f"TORCH_HOME={scratch / 'torch'}", "LANG=C.UTF-8",
        "PYTHONUNBUFFERED=1", "PYTHONDONTWRITEBYTECODE=1", "TOKENIZERS_PARALLELISM=false",
        "OMP_NUM_THREADS=16", "OPENBLAS_NUM_THREADS=16", "HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1"]
    for key in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES", "LD_LIBRARY_PATH"):
        if os.environ.get(key):
            env.append(f"{key}={os.environ[key]}")
    # The root-owned wrapper installs a socket filter before dropping UID. The
    # verifier's audit network access must never reach candidate code.
    return ["/usr/bin/env", "-i", *env, "/opt/conda/bin/python",
            "/tests/offline_exec.py", "submission", *arguments]


def directory(path, candidate=False):
    path.mkdir(mode=0o700)
    if candidate:
        os.chown(path, UID, GID)


def freeze(path):
    # Never follow submission-created symlinks while changing ownership/modes.
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs+files:
            p = Path(root)/name
            info = p.lstat()
            if stat.S_ISLNK(info.st_mode):
                os.chown(p, 0, GID, follow_symlinks=False)
                continue
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise VerificationError("Index contains a non-file artifact")
            os.chown(p, 0, GID, follow_symlinks=False)
            p.chmod(0o550 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o440)
    os.chown(path, 0, GID)
    path.chmod(0o550)


def boundary(scratch):
    checks = ["test -r /task/data/corpus.jsonl", "test -r /task/models/Llama-3.2-1B/model.safetensors",
        "test -x /app/build.sh", "test -x /app/run.sh", "test ! -w /app",
        "test ! -r /tests/data/queries.jsonl", "test ! -r /tests/data/ground_truth.jsonl",
        "test ! -r /tests/grader.py", "test ! -w /logs/verifier", "test ! -e /task/data/examples.jsonl",
        "test ! -r /logs/agent/trajectory.json", "test ! -w /logs/agent",
        'test -z "${OPENAI_API_KEY+x}"', 'test -z "${OPENROUTER_API_KEY+x}"',
        'test -z "${JINA_API_KEY+x}"', 'test -z "${CODEX_HOME+x}"']
    result = subprocess.run(command(["/bin/sh", "-c", " && ".join(checks)], scratch), timeout=10,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise VerificationError("Submission isolation boundary failed")


class Service:
    def __init__(self, scratch, label):
        self.stderr = (LOGS/f"{label}.stderr.log").open("wb")
        self.process = subprocess.Popen(command(["/app/run.sh", "--index-dir", str(INDEX), "--serve"], scratch),
            cwd="/app", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, start_new_session=True, bufsize=0)
        self.reader = self.process.stdout.fileno()
        self.writer = self.process.stdin.fileno()
        os.set_blocking(self.reader, False)
        os.set_blocking(self.writer, False)
        self.pending = bytearray()

    def read_line(self, deadline):
        with selectors.DefaultSelector() as select:
            select.register(self.reader, selectors.EVENT_READ)
            while True:
                if b"\n" in self.pending:
                    line, _, extra = self.pending.partition(b"\n")
                    self.pending = bytearray(extra)
                    value = strict_json(line.decode("utf-8"))
                    if time.perf_counter() > deadline:
                        raise VerificationError("Service deadline exceeded")
                    return value
                remaining = deadline-time.perf_counter()
                if remaining <= 0 or not select.select(remaining):
                    raise VerificationError("Service deadline exceeded")
                chunk = os.read(self.reader, 65536)
                if not chunk:
                    raise VerificationError("Service exited before completing its response")
                self.pending.extend(chunk)
                if len(self.pending) > 16*1024*1024:
                    raise VerificationError("Invalid oversized protocol response")

    def ready(self):
        value = self.read_line(time.perf_counter()+LOAD_SECONDS)
        if value != {"status": "ready"}:
            raise VerificationError("Missing readiness response")

    def request(self, queries, seconds):
        # Evaluator-side JSON serialization is identical across submissions and
        # is excluded. Pipe transfer and response JSON decoding are timed.
        payload = (json.dumps({"queries": queries, "top_k": 10}, separators=(",", ":"), ensure_ascii=False)+"\n").encode()
        if self.pending:
            raise VerificationError("Unsolicited service output")
        start = time.perf_counter()
        deadline = start+seconds
        view = memoryview(payload)
        with selectors.DefaultSelector() as select:
            select.register(self.writer, selectors.EVENT_WRITE)
            while view:
                remaining = deadline-time.perf_counter()
                if remaining <= 0 or not select.select(remaining):
                    raise VerificationError("Query transfer deadline exceeded")
                try:
                    n = os.write(self.writer, view)
                except BrokenPipeError as exc:
                    raise VerificationError("Service closed its input") from exc
                view = view[n:]
        response = self.read_line(deadline)
        return response, time.perf_counter()-start

    def close(self):
        exited = self.process.poll()
        stop_children()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        self.stderr.close()
        self.process.stdin.close()
        self.process.stdout.close()
        if exited is not None and exited != 0:
            raise VerificationError(f"Service exited with status {exited}")


def load_data():
    corpus = {}
    for i, row in enumerate(read_rows(PUBLIC/"corpus.jsonl")):
        if row["doc_id"] in corpus:
            raise VerificationError("Duplicate corpus document ID")
        corpus[row["doc_id"]] = (row["collection"], i)
    queries = read_rows(PRIVATE/"queries.jsonl")
    gold = {r["query_id"]: r for r in read_rows(PRIVATE/"ground_truth.jsonl")}
    if len(corpus) != CORPUS_COUNT or len(queries) != QUERY_COUNT or len(gold) != QUERY_COUNT:
        raise VerificationError("Wrong fixed input counts")
    if {r["query_id"] for r in queries} != gold.keys():
        raise VerificationError("Query/qrel mismatch")
    for qid, row in gold.items():
        if any(d not in corpus or corpus[d][0] != row["collection"] for d in row["relevance"]):
            raise VerificationError("Reference outside its collection")
    return corpus, queries, gold, read_rows(PRIVATE/"warmup.jsonl")


def evaluate():
    if MINIMUM_QUALITY is None or FAST_SECONDS is None or SLOW_SECONDS is None:
        raise VerificationError("Calibration not finalized")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(mode=0o711)
    directory(INDEX, True)
    scratch = WORK/"build-tmp"
    directory(scratch, True)
    boundary(scratch)
    corpus, queries, gold, warmup = load_data()
    start = time.perf_counter()
    with (LOGS/"build.stdout.log").open("wb") as stdout, (LOGS/"build.stderr.log").open("wb") as stderr:
        try:
            result = subprocess.run(command(["/app/build.sh", "--corpus", str(PUBLIC/"corpus.jsonl"),
                "--index-dir", str(INDEX)], scratch), cwd="/app", stdout=stdout, stderr=stderr,
                timeout=BUILD_SECONDS, start_new_session=True)
            build_seconds = time.perf_counter()-start
        finally:
            stop_children()
    if result.returncode != 0 or build_seconds > BUILD_SECONDS:
        raise VerificationError("Index build failed or exceeded its deadline")
    shutil.rmtree(scratch)
    freeze(INDEX)
    timings, scores, reports = [], [], []
    for repeat in range(REPEATS):
        scratch = WORK/f"runtime-{repeat}"
        directory(scratch, True)
        service = Service(scratch, f"service-{repeat}")
        try:
            service.ready()
            response, _ = service.request(warmup, WARMUP_SECONDS)
            validate_response(response, warmup, corpus)
            ordered = list(queries)
            random.SystemRandom().shuffle(ordered)
            mapping, runtime_queries = {}, []
            for q in ordered:
                runtime_id = "request_"+secrets.token_hex(16)
                mapping[runtime_id] = q["query_id"]
                runtime_queries.append({**q, "query_id": runtime_id})
            response, elapsed = service.request(runtime_queries, QUERY_SECONDS)
            valid = validate_response(response, runtime_queries, corpus)
            predictions = {mapping[qid]: ids for qid, ids in valid.items()}
            q, collections, detail = quality(predictions, gold)
            timings.append(elapsed)
            scores.append(q)
            reports.append({"repeat": repeat, "elapsed_seconds": elapsed, "ndcg_at_10": q,
                            "collections": collections})
            write_json(LOGS/f"query-details-{repeat}.json", detail)
        finally:
            service.close()
            shutil.rmtree(scratch)
    elapsed = statistics.median(timings)
    q = min(scores)
    reward = speed_reward(q, elapsed, MINIMUM_QUALITY, FAST_SECONDS, SLOW_SECONDS)
    return {"task_id": TASK, "valid": True, "build_seconds": build_seconds,
        "query_count": QUERY_COUNT, "ndcg_at_10": q, "quality_threshold": MINIMUM_QUALITY,
        "quality_gate_passed": q >= MINIMUM_QUALITY, "median_query_seconds": elapsed,
        "fast_seconds": FAST_SECONDS, "slow_seconds": SLOW_SECONDS, "runs": reports, "reward": reward}


def main():
    LOGS.mkdir(exist_ok=True, mode=0o700)
    (LOGS/"reward.txt").write_text("0\n")
    write_json(LOGS/"reward.json", {"reward": 0})
    try:
        report = evaluate()
        write_json(LOGS/"report.json", report)
        # report.json contains the raw retrieval score. Only finalize_reward.py
        # may award it after a successful integrity audit; public reward stays 0.
        print(json.dumps(report, ensure_ascii=False))
    except Exception as exc:
        stop_children()
        write_json(LOGS/"report.json", {"task_id": TASK, "valid": False, "reward": 0,
                                       "error": type(exc).__name__+": "+str(exc)})
        print(f"Verification failed: {type(exc).__name__}: {exc}", flush=True)
        raise


if __name__ == "__main__":
    main()
