#!/usr/bin/env python3
"""Protected, sequential-query verifier. No hidden labels enter child processes."""
import json
import math
import os
from pathlib import Path
import random
import secrets
import shutil
import signal
import stat
import subprocess
import time

from scoring import VerificationError, strict_json, validate_row, ndcg_at_10, normalized_reward

TASK_ID = "quantity-aware-retrieval"
TASK_DATA = Path("/task/data")
PRIVATE = Path("/tests/data")
WORK = Path("/tmp/quantity-aware-retrieval-eval")
INDEX = WORK / "index"
INPUT = WORK / "input"
OUTPUT = WORK / "output"
LOGS = Path("/logs/verifier/quantity-aware-retrieval-eval")
UID = GID = 10001
CORPUS_COUNT = 153252
QUERY_COUNT = 209
BASELINE_NDCG = 0.1847
BUILD_TIMEOUT_SECONDS = 1200
QUERY_TIMEOUT_SECONDS = 5


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_jsonl(path):
    with path.open() as stream:
        return [strict_json(line) for line in stream if line.strip()]


def child_command(command):
    environment = ["PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "USER=submission",
        "LOGNAME=submission", f"HOME={INDEX}", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1", "TOKENIZERS_PARALLELISM=false",
        "OMP_NUM_THREADS=2", "OPENBLAS_NUM_THREADS=1", "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1", f"TMPDIR={INDEX / 'tmp'}", f"XDG_CACHE_HOME={INDEX / 'cache'}",
        f"HF_HOME={INDEX / 'cache/huggingface'}", f"TORCH_HOME={INDEX / 'cache/torch'}"]
    # Judge/agent credentials and verifier state are deliberately absent.
    for name in ("OPENROUTER_API_KEY", "JINA_API_KEY", "http_proxy", "https_proxy",
                 "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "no_proxy",
                 "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES",
                 "LD_LIBRARY_PATH"):
        value = os.environ.get(name)
        if value:
            environment.append(f"{name}={value}")
    return ["/usr/sbin/runuser", "-u", "submission", "--", "/usr/bin/setpriv",
            "--no-new-privs", "/usr/bin/env", "-i", *environment, *command]


def stop_children():
    for sig in ("TERM", "KILL"):
        subprocess.run(["/usr/bin/pkill", "-" + sig, "-u", "submission"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if sig == "TERM":
            time.sleep(.2)


def kill_group(process):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        if sig == signal.SIGTERM:
            time.sleep(.05)


def run_timed(command, timeout, label):
    started = time.monotonic()
    with (LOGS / f"{label}.stdout.log").open("wb") as stdout, (LOGS / f"{label}.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(child_command(command), cwd="/app", stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        try:
            status = process.wait(timeout=max(0, timeout - (time.monotonic() - started)))
            elapsed = time.monotonic() - started
            timed_out = elapsed > timeout
        except subprocess.TimeoutExpired:
            elapsed, timed_out = time.monotonic() - started, True
            kill_group(process)
            try:
                status = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                status = None
        if timed_out:
            kill_group(process)
    return {"returncode": status, "elapsed_seconds": elapsed, "timed_out": timed_out}


def prepare_workspace():
    if WORK.is_symlink() or (WORK.exists() and not WORK.is_dir()):
        WORK.unlink()
    elif WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(mode=0o711)
    for path, owner, group in [(INDEX, UID, GID), (INPUT, 0, GID), (OUTPUT, UID, GID)]:
        path.mkdir(mode=0o750)
        os.chown(path, owner, group)
    for name in ("tmp", "cache"):
        path = INDEX / name
        path.mkdir(mode=0o700)
        os.chown(path, UID, GID)


def check_boundary():
    checks = ["test -r /task/data/corpus.jsonl", "test -r /task/models/Qwen3-Embedding-0.6B/model.safetensors",
        "test -x /app/build.sh", "test -x /app/run.sh", "test ! -w /app",
        "test ! -r /tests/data/queries.jsonl", "test ! -r /tests/data/ground_truth.jsonl",
        "test ! -r /tests/grader.py", "test ! -r /logs/agent/trajectory.json",
        "test ! -w /logs/agent", "test ! -w /logs/verifier",
        'test -z "${OPENAI_API_KEY+x}"', 'test -z "${OPENAI_BASE_URL+x}"',
        'test -z "${CODEX_HOME+x}"']
    result = subprocess.run(child_command(["/bin/sh", "-c", " && ".join(checks)]),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    if result.returncode:
        raise VerificationError("Submission permission/credential boundary failed")


def load_data():
    corpus_order = {}
    for row in read_jsonl(TASK_DATA / "corpus.jsonl"):
        doc_id = row.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id or doc_id in corpus_order or not isinstance(row.get("text"), str):
            raise VerificationError("Invalid corpus")
        corpus_order[doc_id] = len(corpus_order)
    if len(corpus_order) != CORPUS_COUNT:
        raise VerificationError("Wrong corpus size")
    queries = read_jsonl(PRIVATE / "queries.jsonl")
    ids = [r.get("query_id") for r in queries]
    if len(ids) != QUERY_COUNT or len(set(ids)) != len(ids):
        raise VerificationError("Wrong private query set")
    if any(not isinstance(r.get("text"), str) or not r["text"] or not isinstance(r.get("query_id"), str) for r in queries):
        raise VerificationError("Invalid query")
    gold = {}
    for row in read_jsonl(PRIVATE / "ground_truth.jsonl"):
        qid, relevant = row.get("query_id"), row.get("relevant_doc_ids")
        if qid not in ids or qid in gold or not isinstance(relevant, list) or not relevant:
            raise VerificationError("Invalid private qrels")
        if len(set(relevant)) != len(relevant) or any(d not in corpus_order for d in relevant):
            raise VerificationError("Invalid positive IDs")
        gold[qid] = set(relevant)
    if set(gold) != set(ids):
        raise VerificationError("Private queries and qrels differ")
    return corpus_order, queries, gold


def read_output(path, runtime_id, corpus_order):
    # Never follow a submission-controlled symlink or block on a FIFO/device.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise VerificationError("Output must be a regular JSONL file")
        with os.fdopen(fd, "r", closefd=False) as stream:
            text = stream.read()
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) != 1:
            raise VerificationError("Expected exactly one output record")
        return validate_row(strict_json(lines[0]), runtime_id, corpus_order)
    finally:
        os.close(fd)


def evaluate():
    prepare_workspace()
    corpus_order, queries, gold = load_data()
    check_boundary()
    build = run_timed(["/app/build.sh", "--corpus", str(TASK_DATA / "corpus.jsonl"),
                       "--index-dir", str(INDEX)], BUILD_TIMEOUT_SECONDS, "build")
    if build["timed_out"] or build["returncode"] != 0:
        raise VerificationError(f"Build failed: {build}")
    random.SystemRandom().shuffle(queries)
    details = []
    for position, query in enumerate(queries):
        qid = query["query_id"]
        runtime_id = "request_" + secrets.token_hex(16)
        query_path = INPUT / f"{position:04d}.jsonl"
        query_path.write_text(json.dumps({"query_id": runtime_id, "text": query["text"]}, ensure_ascii=False) + "\n")
        os.chown(query_path, 0, GID)
        query_path.chmod(0o440)
        output_path = OUTPUT / f"{position:04d}.jsonl"
        timing = run_timed(["/app/run.sh", "--index-dir", str(INDEX), "--queries", str(query_path),
                            "--output", str(output_path), "--top-k", "10"],
                           QUERY_TIMEOUT_SECONDS, f"query-{position:04d}")
        if timing["timed_out"]:
            # Ignore even a correct file produced by a call missing its deadline.
            returned = []
        elif timing["returncode"] != 0:
            raise VerificationError(f"Query execution failed: {qid}: {timing}")
        else:
            returned = read_output(output_path, runtime_id, corpus_order)
        value = ndcg_at_10(returned, gold[qid])
        details.append({"query_id": qid, "ndcg_at_10": value, "returned_doc_ids": returned, **timing})
    raw = math.fsum(row["ndcg_at_10"] for row in details) / len(details)
    reward = normalized_reward(raw, BASELINE_NDCG)
    durations = sorted(row["elapsed_seconds"] for row in details)
    return {"task_id": TASK_ID, "valid": True, "query_count": len(details), "build": build,
            "raw_ndcg_at_10": raw, "baseline_ndcg_at_10": BASELINE_NDCG,
            "primary_metric": {"name": "Normalized nDCG@10", "value": reward, "raw_value": raw},
            "reward": reward, "timed_out_queries": sum(r["timed_out"] for r in details),
            "p95_query_seconds": durations[math.ceil(.95 * len(durations)) - 1],
            "max_query_seconds": max(durations), "queries": details}


def main():
    if os.getuid() != 0 or not Path("/.dockerenv").exists() or not PRIVATE.is_dir():
        raise RuntimeError("Run only inside the disposable task verifier container")
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        setup_error = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")
        if setup_error:
            raise VerificationError(setup_error)
        report = evaluate()
    except Exception as error:
        report = {"task_id": TASK_ID, "valid": False, "reward": 0.0,
                  "errors": [f"{type(error).__name__}: {error}"]}
    finally:
        stop_children()
    write_json(LOGS / "evaluation.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "queries"}, allow_nan=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
