#!/usr/bin/env python3
"""Run each hidden query independently and retain successful outputs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

MAX_OUTPUT_BYTES = 64 * 1024 * 1024


def submission_env():
    env = {
        "HOME": "/home/submission", "USER": "submission", "LOGNAME": "submission",
        "PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1", "TOKENIZERS_PARALLELISM": "false",
    }
    for key in ("OPENROUTER_API_KEY", "JINA_API_KEY", "HTTP_PROXY", "HTTPS_PROXY",
                "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        time.sleep(0.1)
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def read_output(path, query_id, limit):
    # Open once without following symlinks, and reject pipes/devices before reading.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("query output is not a regular file within its size limit")
        payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("query output exceeds its size limit")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if (len(rows) != 1 or not isinstance(rows[0], dict)
            or rows[0].get("query_id") != query_id):
        raise ValueError("expected exactly one output matching the input query_id")
    encoded = json.dumps(rows[0], ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError("query output exceeds its size limit")
    return encoded


def run_query(position, query, args, deadline):
    query_id = query["query_id"]
    stem = f"query-{position:03d}"
    input_path = args.queries.parent / f"{stem}.jsonl"
    output_path = args.output_dir / f"{stem}.jsonl"
    input_path.write_text(json.dumps(query) + "\n", encoding="utf-8")
    os.chown(input_path, 0, 10001)
    input_path.chmod(0o440)
    started = time.monotonic()
    encoded, error, code = None, None, None
    try:
        remaining = deadline - started
        if remaining <= 0:
            raise ValueError("shared query execution budget exhausted before launch")
        timeout = min(args.timeout, remaining)
        with (args.logs_dir / f"{stem}.stdout.log").open("w") as stdout, \
                (args.logs_dir / f"{stem}.stderr.log").open("w") as stderr:
            process = subprocess.Popen(
                ["/usr/bin/setpriv", "--no-new-privs", str(args.run_script),
                 "--index-dir", str(args.index_dir), "--queries", str(input_path),
                 "--output", str(output_path), "--top-k", "5"],
                cwd=args.run_script.parent, env=submission_env(),
                stdout=stdout, stderr=stderr, start_new_session=True,
                user=10001, group=10001, extra_groups=[],
            )
            try:
                code = process.wait(timeout=timeout)
            finally:
                stop_group(process)
        if code != 0:
            raise ValueError(f"run.sh exited with status {code}")
        encoded = read_output(output_path, query_id, args.output_limit)
    except subprocess.TimeoutExpired:
        error = f"query exceeded its {timeout:g}-second execution allowance"
    except (OSError, ValueError, UnicodeError) as exc:
        error = str(exc)
    return encoded, {
        "query_id": query_id, "returncode": code,
        "elapsed_seconds": time.monotonic() - started, "error": error,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logs-dir", type=Path, required=True)
    parser.add_argument("--run-script", type=Path, default=Path("/app/run.sh"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--total-timeout", type=float, default=1800)
    parser.add_argument("--concurrency", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()
    if args.timeout <= 0 or args.total_timeout <= 0:
        parser.error("timeouts must be positive")
    queries = [json.loads(line) for line in args.queries.read_text().splitlines() if line.strip()]
    if (not queries or any(not isinstance(q, dict) or not isinstance(q.get("query_id"), str)
                           or not q["query_id"] for q in queries)
            or len({q["query_id"] for q in queries}) != len(queries)):
        raise ValueError("queries must have distinct nonempty string IDs")
    args.output_limit = MAX_OUTPUT_BYTES // len(queries)
    args.logs_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + args.total_timeout
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(run_query, position, query, args, deadline)
                   for position, query in enumerate(queries, 1)]
        results = [future.result() for future in futures]
    manifest = {
        "query_count": len(queries), "concurrency": args.concurrency,
        "per_query_timeout_seconds": args.timeout,
        "shared_timeout_seconds": args.total_timeout,
        "per_query_output_limit_bytes": args.output_limit,
        "elapsed_seconds": time.monotonic() - started,
        "queries": [timing for _, timing in results],
    }
    (args.logs_dir.parent / "query_execution.json").write_text(json.dumps(manifest, indent=2) + "\n")
    args.output.write_text("".join(encoded for encoded, _ in results if encoded is not None))
    # Individual failures are recorded above and receive zero in the grader.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
