#!/usr/bin/env python3
"""Deterministic, separate-process verifier for the filtered Faiss backend."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import pwd
import selectors
import signal
import subprocess
import sys
import time

import faiss
import numpy as np

from checks import check_result
from data_io import read_metadata, read_vectors


HIDDEN_QUERY_COUNT = 10
BUILD_TIMEOUT_SECONDS = 600.0
QUERY_TIMEOUT_SECONDS = 0.015
THREADS = 8


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Process:
    def __init__(self, command, app, work, log, run_as, threads):
        self.log = log.open("wb")
        environment = {
            "PATH": f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(work), "TMPDIR": str(work / "tmp"),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": str(threads), "OPENBLAS_NUM_THREADS": "1",
            "OMP_WAIT_POLICY": "PASSIVE",
            "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        }
        if run_as:
            # The verifier can contact its trajectory judge; submitted build and
            # query processes inherit an Internet-socket block before dropping uid.
            command = [sys.executable, str(Path(__file__).with_name("offline_exec.py")),
                       run_as, *command]
        self.proc = subprocess.Popen(command, cwd=app, env=environment,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.log, bufsize=0, start_new_session=True)
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        os.set_blocking(self.proc.stdin.fileno(), False)
        self.writer = selectors.DefaultSelector()
        self.writer.register(self.proc.stdin, selectors.EVENT_WRITE)

    def readline(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("submission response timed out")
            if not self.selector.select(remaining):
                if deadline is not None:
                    raise TimeoutError("submission response timed out")
                continue
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("submission exited or closed stdout before replying")
            self.buffer.extend(chunk)
            if len(self.buffer) > 2 * 1024 * 1024:
                raise ValueError("submission output exceeds the protocol limit")
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        return json.loads(line)

    def request(self, query, timeout):
        payload = (json.dumps(query, separators=(",", ":")) + "\n").encode()
        started = time.monotonic()
        deadline = started + timeout
        pending = memoryview(payload)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{query['query_id']}: query deadline expired while sending request")
            try:
                written = os.write(self.proc.stdin.fileno(), pending)
            except BlockingIOError:
                if not self.writer.select(max(0.0, deadline - time.monotonic())):
                    raise TimeoutError(f"{query['query_id']}: query deadline expired while sending request")
                continue
            pending = pending[written:]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"{query['query_id']}: query deadline expired while sending request")
        result = self.readline(remaining)
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise TimeoutError(f"{query['query_id']}: query including JSON decode took {elapsed:.6f}s, limit {timeout:.6f}s")
        return result, elapsed

    def build_wait(self, timeout):
        # Drain ordinary build output; never let a full stdout pipe deadlock it.
        deadline = time.monotonic() + timeout
        while self.proc.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("build exceeded the time limit")
            if self.selector.select(0.1):
                chunk = os.read(self.proc.stdout.fileno(), 65536)
                self.log.write(chunk)
        if self.proc.returncode != 0:
            raise RuntimeError(f"build exited with code {self.proc.returncode}")

    def close(self):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait()
        self.selector.close()
        self.writer.close()
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.log.close()


def check_index_files(path):
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError("persistent index files must not be symbolic links")


def inspect_faiss(path, rows, dimension):
    filename = path / "index.faiss"
    if not filename.is_file() or filename.is_symlink():
        raise ValueError("save must produce a regular index.faiss file")
    index = faiss.read_index(str(filename))
    if index.ntotal != rows or index.d != dimension or not index.is_trained:
        raise ValueError("Faiss index has incorrect count/dimension or is not trained")
    if index.metric_type != faiss.METRIC_L2:
        raise ValueError("the persisted Faiss index must use L2")
    base = index
    while hasattr(base, "index"):
        base = faiss.downcast_index(base.index)
    if isinstance(base, faiss.IndexFlat):
        raise ValueError("an exact-only IndexFlat is not an ANN corpus index")
    return {"class": type(index).__name__, "ntotal": int(index.ntotal),
            "dimension": int(index.d)}


def ensure_owned(path, run_as):
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o755)
    if run_as:
        user = pwd.getpwnam(run_as)
        os.chown(path, user.pw_uid, user.pw_gid)


def check_quality(retrieval):
    cases = retrieval["queries"]
    if len(cases) != HIDDEN_QUERY_COUNT or len({q["query_id"] for q in cases}) != HIDDEN_QUERY_COUNT:
        raise ValueError(f"expected exactly {HIDDEN_QUERY_COUNT} distinct test cases")
    for case in cases:
        if type(case["score"]) is not int or case["score"] not in (0, 1):
            raise ValueError("per-query score must be 0 or 1")
    return sum(case["score"] for case in cases) / HIDDEN_QUERY_COUNT


def score_query(process, query, gold, vectors, metadata, timeout):
    """Keep correctness/protocol/deadline failures local to this request."""
    detail = {"query_id": query["query_id"], "group": gold["group"],
              "recall": 0.0, "seconds": 0.0, "score": 0, "error": None}
    started = time.monotonic()
    try:
        result, elapsed = process.request(query, timeout)
    except (OSError, ValueError, RuntimeError, RecursionError) as error:
        detail.update(seconds=time.monotonic() - started,
                      error=f"{type(error).__name__}: {error}")
        # A late/partial reply must not be consumed as the next query's answer.
        return detail, None, True
    detail["seconds"] = elapsed
    try:
        detail["recall"] = check_result(query, result, gold, vectors, metadata)
    except (ValueError, TypeError, OverflowError) as error:
        detail["error"] = f"{type(error).__name__}: {error}"
        return detail, None, True
    detail["score"] = int(detail["recall"] == 1.0)
    if not detail["score"]:
        detail["error"] = "exact filtered Top-K required"
    return detail, result, False


def run_stage(args, name, corpus, query_file, gold_file):
    app, work = args.app, args.work_dir / name
    work.mkdir(parents=True, exist_ok=True)
    work.chmod(0o755)
    index = work / "index"
    ensure_owned(index, args.run_as)
    ensure_owned(index / "tmp", args.run_as)
    vectors, metadata = read_vectors(corpus / "vectors.u8bin"), read_metadata(corpus / "metadata.spmat")
    queries = read_jsonl(query_file)
    gold_rows = read_jsonl(gold_file)
    gold = {g["query_id"]: g for g in gold_rows}
    if (len(gold) != len(gold_rows) or len(gold) != len(queries)
            or {q["query_id"] for q in queries} != set(gold)):
        raise ValueError("private query/ground-truth coverage mismatch")
    if len(queries) != HIDDEN_QUERY_COUNT:
        raise ValueError(f"expected exactly {HIDDEN_QUERY_COUNT} test queries")
    started = time.monotonic()
    process = Process([str(app / "build.sh"), "--vectors", str(corpus / "vectors.u8bin"),
                       "--metadata", str(corpus / "metadata.spmat"), "--index-dir", str(index)],
                      app, index, args.report.parent / f"{name}-build.log",
                      args.run_as, THREADS)
    try:
        process.build_wait(BUILD_TIMEOUT_SECONDS)
    finally:
        process.close()
    build_seconds = time.monotonic() - started
    check_index_files(index)
    faiss_info = inspect_faiss(index, len(vectors), vectors.shape[1])
    # Retire the paths supplied to build, retaining the verifier's open maps.
    # The official run uses aliases to avoid copying the 10M corpus.
    retired_input = work / "retired-build-input"
    corpus.rename(retired_input)
    retired_input.chmod(0o700)

    timings, details, initial_details = [], [], []
    first_responses = {}
    load_times = []
    phases = [queries, queries]
    for phase, requests in enumerate(phases):
        if phase:
            relocated = work / "restored-index"
            index.rename(relocated)
            index = relocated
        ensure_owned(index / "tmp", args.run_as)
        process = None
        try:
            for number, query in enumerate(requests):
                if process is None:
                    started = time.monotonic()
                    process = Process([str(app / "run.sh"), "--index-dir", str(index), "--serve"],
                                      app, index, args.report.parent / f"{name}-serve-{phase}-{number}.log",
                                      args.run_as, THREADS)
                    # Startup is bounded by test.sh's overall verifier timeout.
                    # The per-query deadline starts when request() sends input.
                    if process.readline() != {"status": "ready"}:
                        raise ValueError("service must emit exactly {\"status\": \"ready\"} after loading")
                    load_times.append(time.monotonic() - started)
                detail, result, restart = score_query(
                    process, query, gold[query["query_id"]], vectors, metadata,
                    QUERY_TIMEOUT_SECONDS)
                if restart:
                    process.close()
                    process = None
                if phase == 0:
                    if detail["score"]:
                        first_responses[query["query_id"]] = result
                    initial_details.append(detail)
                    continue
                detail["reload_score"] = detail["score"]
                detail["first_pass_score"] = initial_details[number]["score"]
                if not detail["first_pass_score"]:
                    detail["score"] = 0
                    detail["error"] = detail["error"] or "query failed before index relocation"
                elif detail["score"] and result != first_responses[query["query_id"]]:
                    detail["score"] = 0
                    detail["error"] = "save/load relocation changed the answer to an identical query"
                timings.append(detail["seconds"])
                details.append(detail)
        finally:
            if process is not None:
                process.close()
    percentile = float(np.percentile(timings, 95)) if timings else 0.0
    check_index_files(index)
    grouped = defaultdict(list)
    for detail in details:
        grouped[detail["group"]].append(detail["score"])
    return {"query_count": len(queries),
            "mean_recall": float(np.mean([d["recall"] for d in details])),
            "mean_score": sum(d["score"] for d in details) / len(queries),
            "groups": {g: {"count": len(values), "mean_score": float(np.mean(values))}
                       for g, values in grouped.items()},
            "build_seconds": build_seconds, "load_seconds": load_times,
            "query_seconds": sum(timings), "p95_seconds": percentile,
            "max_query_seconds": max((detail["seconds"] for detail in details + initial_details), default=0.0),
            "request_count_including_reload_checks": len(details) + len(initial_details),
            "pre_reload_queries": initial_details,
            "faiss": faiss_info, "queries": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("/app"))
    parser.add_argument("--corpus", type=Path, default=Path("/task/data/corpus"))
    parser.add_argument("--private-data", type=Path, default=Path("/tests/data"))
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/task-1-x-1-eval"))
    parser.add_argument("--report", type=Path, default=Path("/logs/verifier/evaluation.json"))
    parser.add_argument("--run-as", default="")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"valid": False, "reward": 0.0, "error": None}
    try:
        # A CPU quota alone permits migration over every host core. Pin both
        # verifier and its submission children to the same available CPUs for
        # reproducible single-request deadlines, respecting container cpusets.
        measured_cpus = sorted(os.sched_getaffinity(0))[:THREADS]
        os.sched_setaffinity(0, measured_cpus)
        report["cpu_affinity"] = measured_cpus
        for name in ["build.sh", "run.sh"]:
            if not (args.app / name).is_file() or not os.access(args.app / name, os.X_OK):
                raise ValueError(f"missing executable {name}")
        if args.work_dir.exists():
            raise ValueError("verifier work directory must be fresh")
        args.work_dir.mkdir(parents=True, mode=0o755)
        staged = args.work_dir / "build-input"
        staged.mkdir(mode=0o755)
        for name in ["vectors.u8bin", "metadata.spmat"]:
            (staged / name).symlink_to((args.corpus / name).resolve())
        report["retrieval"] = run_stage(args, "retrieval", staged,
                                        args.private_data / "queries.jsonl",
                                        args.private_data / "ground_truth.jsonl")
        metric = check_quality(report["retrieval"])
        report["query_count"] = HIDDEN_QUERY_COUNT
        report["passed_queries"] = sum(q["score"] for q in report["retrieval"]["queries"])
        report["all_cases_passed"] = report["passed_queries"] == HIDDEN_QUERY_COUNT
        report["primary_metric"] = {"name": "ExactFilteredTop10Accuracy", "value": metric,
                                    "query_count": HIDDEN_QUERY_COUNT,
                                    "per_query_latency_gate": True, "all_queries_required": False}
        report["valid"] = True
        report["reward"] = metric
        report["score"] = 100.0 * metric
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    write_json(args.report, report)
    (args.report.parent / "reward.txt").write_text(f"{report['reward']:.10f}\n")
    write_json(args.report.parent / "reward.json", {"reward": report["reward"]})
    print(json.dumps({"valid": report["valid"], "reward": report["reward"], "error": report["error"]}))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
