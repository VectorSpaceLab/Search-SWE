"""Trusted event controller for the fixed incremental-search workload."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from runtime_limits import LIMITS
import os
from pathlib import Path
import shutil
import signal
import sys
import time

import numpy as np
import faiss

from metrics import KS, TOTAL_NEIGHBORS, dataset_score, recall, error_gain, missing_neighbors
from kernel import kernel_signature, require_truth_kernel
from process import Process

UID = 10001
GIB = 1024**3
EXACT_SCAN_FRACTION = .10
MIN_BASELINE_MISSES = 100
ROOT = Path(__file__).resolve().parent
PUBLIC, PRIVATE, WORK, LOG = map(Path, ["/task/public", "/private", "/work", "/logs/verifier"])


def submission_tasks():
    for process in Path("/proc").iterdir():
        if process.name.isdigit():
            try:
                if process.stat().st_uid == UID:
                    yield from process.joinpath("task").iterdir()
            except FileNotFoundError:
                pass


def affinity(cpus):
    tasks = [int(task.name) for task in submission_tasks()]
    previous = os.geteuid()
    try:
        # The controller retains its real/saved root UID. Matching the candidate's
        # effective UID permits this operation without adding SYS_NICE to Docker.
        os.seteuid(UID)
        for task in tasks:
            try:
                os.sched_setaffinity(task, cpus)
            except ProcessLookupError:
                pass
    finally:
        os.seteuid(previous)


def stop_submission():
    for task in submission_tasks():
        try:
            os.kill(int(task.name), signal.SIGKILL)
        except ProcessLookupError:
            pass


def pause_submission():
    deadline = time.monotonic() + 2
    while True:
        running = False
        for task in submission_tasks():
            try:
                state = next(line for line in (task / "status").read_text().splitlines()
                             if line.startswith("State:"))
                if "T (stopped)" not in state and "Z (zombie)" not in state:
                    os.kill(int(task.name), signal.SIGSTOP)
                    running = True
            except (FileNotFoundError, ProcessLookupError):
                pass
        if not running:
            return
        if time.monotonic() > deadline:
            raise RuntimeError("Cannot suspend submission for trusted scoring")
        time.sleep(.001)


def resume_submission():
    for task in submission_tasks():
        try:
            os.kill(int(task.name), signal.SIGCONT)
        except ProcessLookupError:
            pass


def tree_bytes(path):
    total = 0
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            item = Path(directory) / name
            try:
                if not item.is_symlink():
                    total += item.stat().st_size
            except FileNotFoundError:
                pass
    return total


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def load_limits():
    calibration = deepcopy(LIMITS)
    if calibration.get("timing_policy") != "same-environment-exact-reference":
        raise RuntimeError("Exact-scan timings must be measured in the evaluation environment")
    fraction = calibration.get("exact_scan_fraction")
    if (type(fraction) not in (int, float) or not np.isfinite(fraction)
            or fraction != EXACT_SCAN_FRACTION):
        raise RuntimeError("Frozen query fraction differs from verifier policy; recalibrate")
    if calibration.get("minimum_baseline_missing_neighbors") != MIN_BASELINE_MISSES:
        raise RuntimeError("Missing stable baseline calibration policy")
    if calibration.get("scoring_policy") != "log-missed-neighbor-gain-over-public-reference":
        raise RuntimeError("Missing public-baseline recall gain policy")
    if calibration.get("total_requested_neighbors") != TOTAL_NEIGHBORS:
        raise RuntimeError("Invalid total requested-neighbor count")
    if len(os.sched_getaffinity(0)) < 16:
        raise RuntimeError("At least 16 allocated logical CPUs are required")
    cpus = calibration.get("cpu_affinity")
    if (not isinstance(cpus, list) or len(cpus) != 16 or
            any(type(cpu) is not int or cpu < 0 for cpu in cpus) or len(set(cpus)) != 16):
        raise RuntimeError("Calibration must identify its 16 allocated logical CPUs")
    if set(cpus) != set(os.sched_getaffinity(0)):
        raise RuntimeError("Calibrated CPUs are unavailable or allocation differs; use the calibrated cpuset in both phases")
    if calibration.get("runtime_signature") != kernel_signature():
        raise RuntimeError("Reference timings use a different Faiss runtime; recalibrate")
    for name, expected in (("exact_search.py", calibration["exact_reference_sha256"]),
                           ("baseline_search.py", calibration["baseline"]["public_sha256"])):
        actual = hashlib.sha256((PUBLIC.parent / "reference" / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError("Public reference changed after calibration; recalibrate")
    for dim in (1536, 3072):
        limits = calibration["datasets"][str(dim)]
        preparation = np.asarray([limits["build_seconds"], limits["insert_seconds"]], dtype=float)
        if not np.isfinite(preparation).all() or (preparation <= 0).any():
            raise RuntimeError("Invalid preparation budgets")
        error_gain(0, limits["baseline_missing_neighbors"])
        if limits["baseline_missing_neighbors"] < MIN_BASELINE_MISSES:
            raise RuntimeError(f"Public baseline must miss at least {MIN_BASELINE_MISSES} neighbors for a stable log anchor")
        baseline_micro_recall = limits["baseline_micro_recall"]
        if (type(baseline_micro_recall) not in (int, float) or not np.isfinite(baseline_micro_recall)
                or not 0 < baseline_micro_recall < 1):
            raise RuntimeError("Public baseline must leave a stable recall gap below perfect retrieval")
        if abs(limits["baseline_missing_neighbors"] / TOTAL_NEIGHBORS - (1 - baseline_micro_recall)) > 1e-8:
            raise RuntimeError("Baseline micro recall and missed-neighbor count disagree")
        full = np.asarray(limits["full_scan_seconds"], dtype=float)
        if full.shape != (10, 5) or not np.isfinite(full).all() or (full <= 0).any():
            raise RuntimeError("Invalid per-stage per-K reference timings")
    return calibration


def boundary_ties(response, target, boundary, query, initial, inserts, live_count):
    """Accept any exact boundary tie, including ties outside the stored Top-1000.

    Recompute with the identical Faiss direct distance primitive. Never trust a
    submission-provided distance to establish membership in the true neighbor set.
    """
    if not isinstance(response, dict) or not isinstance(response.get("ids"), list):
        return set()
    if len(response["ids"]) > len(target):
        return set()
    known = set(int(i) for i in target)
    tied = set()
    for identifier in set(i for i in response["ids"] if type(i) is int):
        if identifier in known or not 0 <= identifier < live_count:
            continue
        vector = initial[identifier] if identifier < len(initial) else inserts[identifier - len(initial)]
        d = faiss.fvec_L2sqr(faiss.swig_ptr(query), faiss.swig_ptr(vector), len(query))
        if np.float32(d) == boundary:
            tied.add(identifier)
    return tied


def evaluate_dataset(dim, limits, *, initial_count=105_000, batch_size=1000, stages=10,
                     selected_cells=None):
    require_truth_kernel(PRIVATE / str(dim))
    stop_submission()
    for name in ("state", "events"):
        path = WORK / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(mode=0o755)
    os.chown(WORK / "state", UID, UID)
    initial = PUBLIC / str(dim) / "initial.npy"
    inserts = np.load(PRIVATE / str(dim) / "inserts.npy", mmap_mode="r")
    queries = np.load(PRIVATE / str(dim) / "queries.npy", mmap_mode="r")
    truth = np.load(PRIVATE / str(dim) / "truth.npy", mmap_mode="r")
    truth_distances = np.load(PRIVATE / str(dim) / "truth_distances.npy", mmap_mode="r")
    if (inserts.shape != (batch_size * stages, dim) or queries.shape != inserts.shape
            or truth.shape != (batch_size * stages, 1000) or truth_distances.shape != truth.shape):
        raise RuntimeError("Invalid fixed dataset shape")
    initial_vectors = np.load(initial, mmap_mode="r")
    if initial_vectors.shape != (initial_count, dim):
        raise RuntimeError("Invalid initial corpus shape")
    cpus = set(sorted(os.sched_getaffinity(0))[:16])
    base_bytes = tree_bytes(Path("/app/submission")) + initial.stat().st_size
    last_check = 0.0
    peak_disk = base_bytes

    def monitor():
        nonlocal last_check, peak_disk
        now = time.monotonic()
        if now - last_check >= .1:
            last_check = now
            peak_disk = max(peak_disk, base_bytes + tree_bytes(WORK) + tree_bytes(LOG))
            if peak_disk > 32 * GIB:
                raise ValueError("Dataset exceeded 32 GiB storage")

    env = {"PATH": "/opt/conda/bin:/usr/bin:/bin", "HOME": "/work/state",
           "TMPDIR": "/work/state", "OMP_NUM_THREADS": "16", "OPENBLAS_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "KMP_AFFINITY": "disabled", "OMP_PROC_BIND": "false",
           "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C.UTF-8"}
    worker = Process([sys.executable, str(ROOT / "isolate.py")], cwd=WORK / "state", env=env,
                     stderr=LOG / f"{dim}.stderr.log", prepare=lambda: os.sched_setaffinity(0, cpus))
    result = {"dimension": dim, "cells": [], "insert_seconds": [], "score": 0.0}
    phase = {"operation": "build"}
    try:
        response = worker.request({"op": "build", "vectors": str(initial), "dimension": dim,
                                   "count": initial_count, "threads": 16, "state_dir": "/work/state"},
                                  worker.started + limits["build_seconds"], monitor)
        result["build_seconds"] = time.monotonic() - worker.started
        if response != {"ok": True}:
            raise ValueError("Build did not acknowledge readiness")
        warmup = np.load(PUBLIC / str(dim) / "warmup.npy")
        # Public warmup belongs to the build limit and only occurs once.
        phase = {"operation": "public_warmup"}
        affinity({min(cpus)})
        for q in warmup:
            worker.request({"op": "search", "vector": q.tolist(), "k": 1000},
                           worker.started + limits["build_seconds"], monitor)
        pause_submission()
        result["build_seconds"] = time.monotonic() - worker.started
        if result["build_seconds"] > limits["build_seconds"]:
            raise TimeoutError("Build including warmup exceeded its budget")
        for stage in range(stages):
            phase = {"operation": "insert", "stage": stage}
            affinity(cpus)
            event = WORK / "events" / "insert.npy"
            np.save(event, inserts[stage * batch_size:(stage + 1) * batch_size])
            event.chmod(0o444)
            start = time.monotonic()
            resume_submission()
            ack = worker.request({"op": "insert", "vectors": str(event), "count": batch_size,
                                  "first_id": initial_count + stage * batch_size, "threads": 16},
                                 start + limits["insert_seconds"], monitor)
            pause_submission()
            result["insert_seconds"].append(time.monotonic() - start)
            if result["insert_seconds"][-1] > limits["insert_seconds"]:
                raise TimeoutError("Insertion exceeded its budget")
            if ack != {"ok": True}:
                raise ValueError("Insert did not acknowledge readiness")
            event.unlink()
            affinity({min(cpus)})
            for ki, k in enumerate(KS):
                if selected_cells is not None and (stage, k) not in selected_cells:
                    continue  # Trusted operator calibration only; production always runs all 50 cells.
                # No pauses for grading: cache computation and background work between
                # consecutive requests are included in this entire cell's wall time.
                responses = []
                phase = {"operation": "query", "stage": stage, "k": k}
                budget = EXACT_SCAN_FRACTION * limits["full_scan_seconds"][stage][ki]
                start = time.monotonic()
                resume_submission()
                for q in queries[stage * batch_size:(stage + 1) * batch_size]:
                    responses.append(worker.request({"op": "search", "vector": q.tolist(), "k": k},
                                                     start + budget, monitor))
                pause_submission()
                seconds = time.monotonic() - start
                # Stop all submission threads while the trusted controller scores outputs.
                # This prevents query cache work from escaping the cell timing window.
                lo, hi = stage * batch_size, (stage + 1) * batch_size
                live = initial_count + (stage + 1) * batch_size
                values = [recall(row, target, k, live,
                          boundary_ties(row, target[:k], distances[k - 1], query,
                                        initial_vectors, inserts, live))
                          for row, target, distances, query in
                          zip(responses, truth[lo:hi], truth_distances[lo:hi], queries[lo:hi])]
                hits = np.rint(np.asarray(values) * k).astype(np.int64)
                result["cells"].append({"stage": stage, "k": k, "seconds": seconds,
                                        "budget_seconds": budget, "recall": sum(values) / batch_size,
                                        "exact_query_fraction": float(np.mean(hits == k)),
                                        "p10_recall": float(np.quantile(values, .1)),
                                        "recall_histogram": np.bincount(hits, minlength=k + 1).tolist()})
                write_json(LOG / f"{dim}.progress.json", result)
                if seconds > budget:
                    raise TimeoutError("Query cell exceeded its budget")
        monitor()
        timed_recall = dataset_score(result["cells"], stages=stages)
        if "baseline_missing_neighbors" in limits:
            missing = missing_neighbors(result["cells"])
            result["score"] = error_gain(missing, limits["baseline_missing_neighbors"]) if timed_recall > 0 else 0.0
        else:
            # Author-only exact/feasibility measurements retain their raw recall.
            result["score"] = timed_recall
    except (ValueError, TimeoutError, BrokenPipeError) as error:
        result["failure"] = str(error)
        result["failure_context"] = phase
    finally:
        stop_submission()
        worker.close()
        result["peak_sampled_disk_bytes"] = peak_disk
        result["mean_recall"] = (sum(c["recall"] for c in result["cells"]) / (stages * len(KS))
                                  if len(result["cells"]) == stages * len(KS) else None)
        result["baseline_micro_recall"] = limits.get("baseline_micro_recall")
        result["missing_neighbors"] = (missing_neighbors(result["cells"])
            if len(result["cells"]) == stages * len(KS) else None)
        result["baseline_missing_neighbors"] = limits.get("baseline_missing_neighbors")
        result["micro_recall"] = (1 - result["missing_neighbors"] / (stages * batch_size * sum(KS))
                                  if result["missing_neighbors"] is not None else None)
        write_json(LOG / f"{dim}.result.json", result)
    return result


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    LOG.chmod(0o700)
    (LOG / "reward.txt").write_text("0\n")
    write_json(LOG / "reward.json", {"reward": 0.0})
    try:
        calibration = load_limits()
        # Reuse the allocation used for calibration, including under quota-only Docker backends.
        os.sched_setaffinity(0, calibration["cpu_affinity"])
        WORK.mkdir(exist_ok=True)
        results = [evaluate_dataset(dim, calibration["datasets"][str(dim)]) for dim in (1536, 3072)]
        reward = sum(r["score"] for r in results) / 2
        write_json(LOG / "evaluation.json", {"valid": True, "datasets": results, "raw_reward": reward})
        # The trajectory audit applies the semantic no-rebuild/integrity gate separately.
        return 0
    except Exception as error:
        write_json(LOG / "evaluation.json", {"valid": False, "error": f"{type(error).__name__}: {error}"})
        return 1
    finally:
        stop_submission()


if __name__ == "__main__":
    raise SystemExit(main())
