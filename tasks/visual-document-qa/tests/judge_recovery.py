"""Trusted judge checkpoints and bounded recovery from temporary service failures."""

import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import random
import tempfile
import threading
import time
from collections import deque


class TemporaryJudgeError(RuntimeError):
    pass


class PermanentJudgeError(RuntimeError):
    pass


class JudgeDeadlineError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def atomic_dump(path, value):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".judge-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_snapshot(path, context, payload):
    atomic_dump(path, {"context": context, "payload": payload, "sha256": digest(payload)})


def load_snapshot(path, context):
    try:
        value = json.loads(Path(path).read_text())
        if value["context"] != context or value["sha256"] != digest(value["payload"]):
            raise ValueError("mismatch")
        return value["payload"]
    except (OSError, ValueError, TypeError, KeyError):
        raise PermanentJudgeError("Judge checkpoint is missing, corrupt or from a different grading context") from None


class SampleStore:
    def __init__(self, root, context):
        self.root = Path(root) / context
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def sample(self, job, index, evaluate):
        key = digest({"job": job, "sample": index})
        path = self.root / (key + ".json")
        cached = path.exists()
        if cached:
            row = load_snapshot(path, key)
        else:
            row = evaluate(job)
        if (not isinstance(row, dict) or row.get("query_id") != job[0]["query_id"]
                or row.get("branch") != job[1]["branch"] or row.get("error") is not None
                or type(row.get("value")) not in (int, float)
                or not math.isfinite(row["value"]) or row["value"] not in (0, 1)):
            raise PermanentJudgeError("Invalid saved judge sample")
        if not cached:
            save_snapshot(path, key, row)
        return row


class Recovery:
    def __init__(self, deadline):
        self.deadline = deadline
        self.ready_at = 0.0
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.deferred_jobs = 0

    def check(self):
        if self.cancelled.is_set():
            raise JudgeDeadlineError("Answer judging stopped; completed samples are preserved")
        if time.monotonic() >= self.deadline:
            raise JudgeDeadlineError("Answer judging time budget exhausted; completed samples are preserved")

    def pause(self, seconds):
        with self.lock:
            self.ready_at = max(self.ready_at, time.monotonic() + seconds)

    def wait(self):
        while True:
            self.check()
            with self.lock:
                delay = self.ready_at - time.monotonic()
            if delay <= 0:
                return
            self.cancelled.wait(min(delay, 1, max(0, self.deadline - time.monotonic())))

    def sleep(self, seconds):
        self.check()
        self.cancelled.wait(min(seconds, max(0, self.deadline - time.monotonic())))
        self.check()


def recover_jobs(jobs, workers, evaluate, recovery):
    """Only unfinished jobs are resubmitted; at most workers futures exist at once."""
    pending = deque(enumerate(jobs))
    active = {}
    ready = {}
    next_result = 0
    failures = {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(jobs) or 1))
    try:
        while pending or active:
            recovery.check()
            while pending and len(active) < workers and time.monotonic() >= recovery.ready_at:
                index, job = pending.popleft()
                active[pool.submit(evaluate, job)] = (index, job)
            if not active:
                recovery.wait()
                continue
            completed, _ = concurrent.futures.wait(
                active, timeout=0.25, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                index, job = active.pop(future)
                try:
                    ready[index] = future.result()
                except TemporaryJudgeError:
                    failures[index] = failures.get(index, 0) + 1
                    recovery.deferred_jobs += 1
                    delay = min(60 * 2 ** min(failures[index] - 1, 3), 300)
                    recovery.pause(delay + random.uniform(0, 5))
                    pending.append((index, job))
                    print("judge temporarily unavailable; preserving progress and deferring unfinished work", flush=True)
            while next_result in ready:
                yield ready.pop(next_result)
                next_result += 1
    finally:
        recovery.cancelled.set()
        pool.shutdown(wait=True, cancel_futures=True)
