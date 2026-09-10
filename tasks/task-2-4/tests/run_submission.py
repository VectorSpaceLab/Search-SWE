#!/usr/bin/env python3
"""Build, repeatedly run, and score a Task-2-4 submission."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import signal
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PRIVATE_ENV_NAMES = {
    "API_KEY",
    "MODEL_API",
    "MODEL_NAME",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
}
AGENT_API_NAMES = {
    "OPENROUTER_API_KEY",
    "JINA_API_KEY",
    "OPENROUTER_API_BASE_URL",
}
UNTRUSTED_UID = 65534
UNTRUSTED_GID = 65534


def submission_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if key in AGENT_API_NAMES:
            continue
        if key in PRIVATE_ENV_NAMES or upper.startswith("SILICONFLOW_") or upper.endswith("_API_KEY") or any(token in upper for token in ("SECRET", "PASSWORD")):
            env.pop(key, None)
    env["HOME"] = "/tmp/task2-4-submission-home"
    env["TMPDIR"] = "/tmp"
    return env


def prepare_untrusted_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("submission must be a real directory")
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                raise ValueError(f"submission contains symlink directory: {child}")
        for name in file_names:
            child = directory_path / name
            child_stat = os.lstat(child)
            if not stat.S_ISREG(child_stat.st_mode):
                raise ValueError(f"submission contains unsafe file: {child}")
            os.chown(child, UNTRUSTED_UID, UNTRUSTED_GID)
            child.chmod(stat.S_IMODE(child_stat.st_mode) & ~0o6000)
        os.chown(directory_path, UNTRUSTED_UID, UNTRUSTED_GID)
        directory_path.chmod(0o755)


def prepare_untrusted_runtime(results: Path) -> None:
    home = Path("/tmp/task2-4-submission-home")
    home.mkdir(parents=True, exist_ok=True)
    os.chown(home, UNTRUSTED_UID, UNTRUSTED_GID)
    home.chmod(0o700)
    os.chown(results, 0, 0)
    results.chmod(0o755)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def load_queries(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"invalid query at line {line_number}")
            query_id = str(record.get("query_id", ""))
            question = record.get("question")
            if not query_id or query_id in seen or not isinstance(question, str) or not question.strip():
                raise ValueError(f"invalid query at line {line_number}")
            seen.add(query_id)
            records.append(record)
    if not records:
        raise ValueError("queries file is empty")
    return records


def kill_group(process_group: int | None) -> None:
    if process_group is None:
        return
    try:
        os.killpg(process_group, signal.SIGTERM)
        time.sleep(0.5)
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_one(
    command: list[str],
    *,
    cwd: Path,
    stdout: Any,
    stderr: Any,
    timeout: float | None,
) -> tuple[int | None, float, str | None]:
    started = time.monotonic()
    process_group: int | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            env=submission_env(),
            start_new_session=True,
            user=UNTRUSTED_UID,
            group=UNTRUSTED_GID,
            extra_groups=[],
        )
        process_group = os.getpgid(process.pid)
        try:
            return process.wait(timeout=timeout), time.monotonic() - started, None
        except subprocess.TimeoutExpired:
            kill_group(process_group)
            return None, time.monotonic() - started, f"command exceeded {timeout} seconds"
    except OSError as error:
        return None, time.monotonic() - started, f"could not start command: {error}"


def required_script(path: Path) -> str | None:
    if not path.is_file():
        return f"missing submission script: {path.name}"
    if not os.access(path, os.X_OK):
        return f"submission script is not executable: {path.name}"
    return None


def run_query(
    position: int,
    query: dict[str, Any],
    submission: Path,
    index_dir: Path,
    results: Path,
    timeout: float | None,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str]]:
    query_id = str(query["query_id"])
    stem = f"query-{position:03d}"
    input_path = results / "query_inputs" / f"{stem}.jsonl"
    output_path = results / "query_outputs" / f"{stem}.jsonl"
    write_jsonl(input_path, [query])
    command = [
        str(submission / "run.sh"), "--index-dir", str(index_dir),
        "--queries", str(input_path), "--output", str(output_path),
    ]
    with (results / "query_logs" / f"{stem}.stdout.log").open("w", encoding="utf-8") as stdout, \
            (results / "query_logs" / f"{stem}.stderr.log").open("w", encoding="utf-8") as stderr:
        code, elapsed, run_error = run_one(
            command, cwd=submission, stdout=stdout, stderr=stderr, timeout=timeout,
        )
    timing = {"query_id": query_id, "returncode": code, "elapsed_seconds": elapsed}
    errors = []
    if run_error:
        errors.append(f"query {query_id}: {run_error}")
    if code != 0:
        if code is not None:
            errors.append(f"query {query_id}: run.sh exited with status {code}")
        return None, timing, errors
    try:
        output_records = []
        with output_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("output record is not an object")
                    output_records.append(record)
        if len(output_records) != 1 or output_records[0].get("query_id") != query_id:
            raise ValueError("expected exactly one output record matching the input query_id")
        return output_records[0], timing, errors
    except (OSError, ValueError) as error:
        errors.append(f"query {query_id}: invalid run output: {error}")
        return None, timing, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission-dir", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--build-timeout", type=float, default=600.0)
    parser.add_argument("--per-query-timeout", type=float, default=None,
                        help="optional diagnostic limit; official verification has no per-query timeout")
    parser.add_argument("--score-timeout", type=float, default=120.0)
    parser.add_argument("--query-concurrency", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()

    submission = args.submission_dir.resolve()
    results = args.results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    report_path = results / "evaluation.json"
    predictions_path = results / "results.jsonl"
    errors: list[str] = []

    try:
        prepare_untrusted_tree(submission)
        prepare_untrusted_runtime(results)
        queries = load_queries(args.queries)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        write_json(report_path, {"valid": False, "score": 0.0, "errors": [str(error)]})
        return 1

    build_script = submission / "build.sh"
    run_script = submission / "run.sh"
    for script in (build_script, run_script):
        error = required_script(script)
        if error:
            errors.append(error)
    if errors:
        write_json(report_path, {"valid": False, "score": 0.0, "errors": errors})
        return 1

    index_dir = submission / "index"
    manifest: dict[str, Any] = {
        "status": "started",
        "query_count": len(queries),
        "phases": {},
    }

    build_stdout = (results / "build.stdout.log").open("w", encoding="utf-8")
    build_stderr = (results / "build.stderr.log").open("w", encoding="utf-8")
    build_command = [
        str(build_script),
        "--corpus",
        str(args.corpus),
        "--index-dir",
        str(index_dir),
    ]
    build_code, build_elapsed, build_error = run_one(
        build_command,
        cwd=submission,
        stdout=build_stdout,
        stderr=build_stderr,
        timeout=args.build_timeout,
    )
    build_stdout.close()
    build_stderr.close()
    manifest["phases"]["build"] = {
        "returncode": build_code,
        "elapsed_seconds": build_elapsed,
    }
    if build_error:
        errors.append(f"build.sh: {build_error}")
    if build_code != 0:
        if build_code is not None:
            errors.append(f"build.sh exited with status {build_code}")
        write_json(report_path, {"valid": False, "score": 0.0, "errors": errors})
        manifest["status"] = "build_failed"
        write_json(results / "run_manifest.json", manifest)
        return 1

    query_inputs = results / "query_inputs"
    query_outputs = results / "query_outputs"
    query_inputs.mkdir(parents=True, exist_ok=True)
    query_outputs.mkdir(parents=True, exist_ok=True)
    os.chown(query_outputs, UNTRUSTED_UID, UNTRUSTED_GID)
    query_outputs.chmod(0o700)
    (results / "query_logs").mkdir(parents=True, exist_ok=True)
    merged: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    run_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.query_concurrency) as executor:
        futures = [
            executor.submit(run_query, position, query, submission, index_dir, results, args.per_query_timeout)
            for position, query in enumerate(queries, 1)
        ]
        # Collect in input order even when queries finish out of order.
        for future in futures:
            record, timing, query_errors = future.result()
            timings.append(timing)
            errors.extend(query_errors)
            if record is not None:
                merged.append(record)
    run_elapsed = time.monotonic() - run_started
    for stream in ("stdout", "stderr"):
        with (results / f"run.{stream}.log").open("w", encoding="utf-8") as combined:
            for position, query in enumerate(queries, 1):
                combined.write(f"=== query {position}: {query['query_id']} ===\n")
                with (results / "query_logs" / f"query-{position:03d}.{stream}.log").open(encoding="utf-8", errors="replace") as log:
                    shutil.copyfileobj(log, combined)
    write_jsonl(predictions_path, merged)
    write_jsonl(results / "per_query_timings.jsonl", timings)
    manifest["phases"]["run"] = {
        "query_count": len(queries),
        "query_concurrency": args.query_concurrency,
        "completed": sum(item["returncode"] == 0 for item in timings),
        "elapsed_seconds": run_elapsed,
        "total_query_elapsed_seconds": sum(item["elapsed_seconds"] for item in timings),
    }
    if errors:
        write_json(report_path, {"valid": False, "score": 0.0, "errors": errors})
        manifest["status"] = "execution_failed"
        write_json(results / "run_manifest.json", manifest)
        return 1

    score_command = [
        sys.executable,
        str(args.evaluator),
        "--predictions",
        str(predictions_path),
        "--queries",
        str(args.queries),
        "--qrels",
        str(args.qrels),
        "--corpus",
        str(args.corpus),
        "--report",
        str(report_path),
    ]
    started = time.monotonic()
    try:
        score_process = subprocess.run(score_command, check=False, timeout=args.score_timeout)
        score_code = score_process.returncode
    except subprocess.TimeoutExpired:
        score_code = None
        write_json(report_path, {"valid": False, "score": 0.0, "errors": ["scoring timed out"]})
    manifest["phases"]["score"] = {
        "returncode": score_code,
        "elapsed_seconds": time.monotonic() - started,
    }
    manifest["status"] = "completed" if score_code == 0 else "score_failed"
    write_json(results / "run_manifest.json", manifest)
    return 0 if score_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
