#!/usr/bin/env python3
"""Run one private question per process with independent query deadlines."""

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
        "PYTHONUNBUFFERED": "1",
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


def run_query(position, query, args):
    query_id = str(query["query_id"])
    stem = f"query-{position:03d}"
    input_path = args.queries.parent / f"{stem}.jsonl"
    output_path = args.output.parent / f"{stem}.jsonl"
    input_path.write_text(json.dumps(query) + "\n", encoding="utf-8")
    os.chown(input_path, 0, 10001)
    input_path.chmod(0o440)
    started = time.monotonic()
    process = None
    record = None
    error = None
    code = None
    try:
        with (args.logs_dir / f"{stem}.stdout.log").open("w") as stdout, \
                (args.logs_dir / f"{stem}.stderr.log").open("w") as stderr:
            process = subprocess.Popen(
                ["/usr/bin/setpriv", "--no-new-privs", str(args.run_script),
                 "--index-dir", str(args.index_dir), "--queries", str(input_path),
                 "--output", str(output_path)],
                cwd=args.run_script.parent, env=submission_env(),
                stdout=stdout, stderr=stderr, start_new_session=True,
                user=10001, group=10001, extra_groups=[],
            )
            try:
                code = process.wait(timeout=args.timeout)
            finally:
                stop_group(process)
        if code != 0:
            raise ValueError(f"run.sh exited with status {code}")
        info = output_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OUTPUT_BYTES:
            raise ValueError("output must be a regular file of at most 64 MiB")
        rows = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]
        if len(rows) != 1 or not isinstance(rows[0], dict) or str(rows[0].get("query_id")) != query_id:
            raise ValueError("expected one output matching the input query_id")
        record = rows[0]
    except subprocess.TimeoutExpired:
        error = f"query exceeded {args.timeout:g} seconds"
    except (OSError, ValueError) as exc:
        error = str(exc)
    return record, {"query_id": query_id, "returncode": code,
                    "elapsed_seconds": time.monotonic() - started, "error": error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logs-dir", type=Path, required=True)
    parser.add_argument("--run-script", type=Path, default=Path("/app/run.sh"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--concurrency", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    queries = [json.loads(line) for line in args.queries.read_text().splitlines() if line.strip()]
    if not queries or len({str(q['query_id']) for q in queries}) != len(queries):
        raise ValueError("queries must have distinct IDs and must not be empty")
    args.logs_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(run_query, position, query, args)
                   for position, query in enumerate(queries, 1)]
        results = [future.result() for future in futures]
    manifest = {"query_count": len(queries), "concurrency": args.concurrency,
                "per_query_timeout_seconds": args.timeout,
                "elapsed_seconds": time.monotonic() - started,
                "queries": [timing for _, timing in results]}
    (args.logs_dir.parent / "query_execution.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output = "".join(json.dumps(record) + "\n" for record, _ in results if record is not None)
    if len(output.encode()) > MAX_OUTPUT_BYTES:
        raise ValueError("merged output exceeds 64 MiB")
    args.output.write_text(output)
    return 1 if any(timing["error"] for _, timing in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
