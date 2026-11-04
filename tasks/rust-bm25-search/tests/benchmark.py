#!/usr/bin/env python3
"""External wall-clock measurement for a persistent JSONL search process.

The controller sends one request at a time, timestamps responses itself,
and never accepts submission-provided timing. It does not evict host caches.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import selectors
import select
import signal
from statistics import median
import subprocess
import time
from pathlib import Path
from itertools import chain

from evaluate import InvalidSubmission, validate_response

MAX_LINE_BYTES = 64 * 1024


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def index_bytes(directory: Path) -> int:
    """Logical file bytes; links, special files and uncounted xattrs are invalid."""
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Index must be a real directory")
    total = 0
    for path in chain([directory], directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Index may not contain symlinks: {path}")
        # Check the root and every directory too. Do not ignore permission or
        # filesystem errors: an index whose metadata cannot be checked fails.
        if os.listxattr(path, follow_symlinks=False):
            raise ValueError(f"Index may not contain extended attributes: {path}")
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise ValueError(f"Index may not contain hard links: {path}")
            total += path.stat().st_size
        elif not path.is_dir():
            raise ValueError(f"Index may not contain special files: {path}")
    if total <= 0:
        raise ValueError("Index is empty")
    return total


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("No observations")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


class SearchProcess:
    def __init__(self, command: list[str], *, stderr: Path, cwd: Path | None = None,
                 env: dict[str, str] | None = None, cleanup=None):
        self.cleanup = cleanup
        self.stderr_stream = stderr.open("wb")
        self.started = time.monotonic()
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.stderr_stream,
                                            cwd=cwd, env=env, start_new_session=True, bufsize=0)
        except BaseException:
            self.stderr_stream.close()
            raise
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = bytearray()
        os.set_blocking(self.process.stdin.fileno(), False)
        self.peak_rss_kib = 0

    def _sample_rss(self) -> None:
        # Diagnostic process high-water mark, not total cgroup memory/page cache.
        # A container memory limit is enforced separately by the operator.
        try:
            for line in Path(f"/proc/{self.process.pid}/status").read_text().splitlines():
                if line.startswith("VmHWM:"):
                    self.peak_rss_kib = max(self.peak_rss_kib, int(line.split()[1]))
                    break
        except (OSError, ValueError):
            pass

    def request(self, query: dict[str, str], *, timeout: float,
                document_count: int) -> tuple[dict, float]:
        if self.buffer:
            raise InvalidSubmission("Unexpected unsolicited output")
        if self.process.poll() is not None:
            raise InvalidSubmission("Search process exited before the request")
        payload = (json.dumps(query, ensure_ascii=False) + "\n").encode()
        if len(payload) > 4096:
            raise ValueError("Query exceeds the protocol's 4096-byte request limit")
        started = time.monotonic()
        deadline = started + timeout
        # Requests fit within PIPE_BUF on the supported Linux runtime.
        pending = memoryview(payload)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Search process did not read its request in time")
            if not select.select([], [self.process.stdin], [], min(remaining, .1))[1]:
                continue
            try:
                written = os.write(self.process.stdin.fileno(), pending)
                pending = pending[written:]
            except BlockingIOError:
                continue
            except BrokenPipeError as error:
                raise InvalidSubmission("Search process closed stdin") from error
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Query {query['query_id']} exceeded its timeout")
            events = self.selector.select(min(remaining, 0.1))
            self._sample_rss()
            if not events:
                continue
            chunk = os.read(self.process.stdout.fileno(), MAX_LINE_BYTES + 1)
            if not chunk:
                raise InvalidSubmission("Search process exited without a complete response")
            self.buffer.extend(chunk)
            if len(self.buffer) > MAX_LINE_BYTES:
                raise InvalidSubmission("Search response exceeds the byte limit")
        finished = time.monotonic()
        line, _, extra = self.buffer.partition(b"\n")
        self.buffer = bytearray(extra)
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise InvalidSubmission("Response is not valid JSON") from error
        validate_response(row, query["query_id"], document_count=document_count)
        return row, finished - started

    def close(self) -> None:
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        # Always terminate the group, including children surviving their parent.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr_stream.close()
        if self.cleanup is not None:
            self.cleanup()

    def __enter__(self):
        return self

    def finish(self) -> None:
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise InvalidSubmission("Search did not exit within five seconds of stdin EOF") from error
        # A descendant may retain stdout after its parent exits. Never block
        # waiting for its EOF; close() terminates the entire submission group.
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            extra = os.read(self.process.stdout.fileno(), MAX_LINE_BYTES + 1)
        except BlockingIOError:
            extra = b""
        if self.buffer or extra:
            raise InvalidSubmission("Unexpected output after the final response")
        if code:
            raise InvalidSubmission(f"Search exited with status {code}")

    def __exit__(self, error_type, *_):
        try:
            if error_type is None:
                self.finish()
        finally:
            self.close()


def measure(command: list[str], *, queries: list[dict], warmup: list[dict],
            directory: Path, document_count: int, timeout: float = 120,
            cold_samples: int = 5, batch_timeout: float = 3600,
            cwd: Path | None = None, env: dict[str, str] | None = None,
            cleanup=None) -> tuple[dict, list[dict]]:
    if not queries or not warmup:
        raise ValueError("Both evaluation and disjoint warmup queries are required")
    if cold_samples < 1 or cold_samples > len(queries):
        raise ValueError("Cold samples must be between one and the query count")
    if timeout <= 0 or batch_timeout <= 0:
        raise ValueError("Timeouts must be positive")
    def normalized_text(q):
        return " ".join(q["text"].casefold().split())
    if ({q["query_id"] for q in queries} & {q["query_id"] for q in warmup}
            or {normalized_text(q) for q in queries} & {normalized_text(q) for q in warmup}):
        raise ValueError("Warmup and measured queries must be disjoint by ID and normalized text")
    directory.mkdir(parents=True, exist_ok=False)
    cold_times, cold_rows, rss = [], [], 0
    # Deterministically distribute samples across the query file; every sample
    # gets a fresh process. This is process-cold, not a claim of cold disk I/O.
    indices = [i * len(queries) // cold_samples for i in range(cold_samples)]
    for sample, index in enumerate(indices):
        with SearchProcess(command, stderr=directory / f"cold-{sample}.stderr.log",
                           cwd=cwd, env=env, cleanup=cleanup) as worker:
            remaining = timeout - (time.monotonic() - worker.started)
            if remaining <= 0:
                raise TimeoutError("Cold process launch exceeded its request budget")
            row, _ = worker.request(queries[index], timeout=remaining, document_count=document_count)
            cold_times.append(time.monotonic() - worker.started)
            cold_rows.append(row)
            rss = max(rss, worker.peak_rss_kib)
    responses, latencies, warm_samples = [], [], []
    first_responses = None
    for repetition in range(5):
        responses = []
        with SearchProcess(command, stderr=directory / f"warm-{repetition}.stderr.log", cwd=cwd, env=env,
                           cleanup=cleanup) as worker:
            warmup_started = time.monotonic()
            for query in warmup:
                remaining = batch_timeout - (time.monotonic() - warmup_started)
                if remaining <= 0:
                    raise TimeoutError("Warmup exceeded its time budget")
                worker.request(query, timeout=min(timeout, remaining), document_count=document_count)
            started = time.monotonic()
            for query in queries:
                remaining = batch_timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Complete measured batch exceeded its time budget")
                row, elapsed = worker.request(query, timeout=min(timeout, remaining),
                                              document_count=document_count)
                responses.append(row)
                latencies.append(elapsed)
            wall = time.monotonic() - started
            rss = max(rss, worker.peak_rss_kib)
        warm_samples.append(wall)
        if first_responses is None:
            first_responses = responses
        elif responses != first_responses:
            raise InvalidSubmission("Repeated warm retrieval results disagree")
    wall = median(warm_samples)
    by_id = {row["query_id"]: row for row in responses}
    for row in cold_rows:
        if row != by_id[row["query_id"]]:
            raise InvalidSubmission("Cold and warm retrieval results disagree")
    with (directory / "results.jsonl").open("w", encoding="utf-8") as stream:
        for row in responses:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    metrics = {
        "query_count": len(queries), "warmup_query_count": len(warmup),
        "warm_seconds": wall, "warm_qps": len(queries) / wall,
        "warm_seconds_samples": warm_samples, "warm_repetitions": 5,
        "warm_aggregation": "median of five complete warm batch seconds",
        "warm_latency_p50_seconds": percentile(latencies, .50),
        "warm_latency_p95_seconds": percentile(latencies, .95),
        "cold_start_to_first_result_seconds": cold_times,
        "cold_start_p50_seconds": percentile(cold_times, .50),
        "cold_start_p95_seconds": percentile(cold_times, .95),
        "cold_samples": cold_samples,
        "cache_policy": "new process; no query warmup; OS file cache is not evicted",
        "sampled_search_process_peak_rss_kib": rss,
        "rss_scope": "search process only; excludes unmapped page cache and child processes",
        "request_concurrency": 1,
    }
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics, responses
