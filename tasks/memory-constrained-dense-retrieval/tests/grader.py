#!/usr/bin/env python3
"""Private verifier for Task memory-constrained-dense-retrieval's memory-constrained vector retrieval."""

from __future__ import annotations

import errno
import json
import math
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


TASK_DATA = Path("/task/data")
PRIVATE_DATA = Path("/tests/data")
SUBMISSION_DIR = Path("/app")
WORK_DIR = Path("/tmp/memory-constrained-dense-retrieval-eval")
INPUT_ROOT = WORK_DIR / "input"
INDEX_DIR = Path("/task/index")
OUTPUT_ROOT = WORK_DIR / "output"
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/memory-constrained-dense-retrieval-eval")
)
REPORT_PATH = RESULTS_DIR / "evaluation.json"
EXECUTION_ERROR = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")

DIMENSION = 1024
VECTOR_DTYPE_BYTES = 4
TOP_K = 3
HIDDEN_QUERY_COUNT = 20
MEASUREMENT_ROUNDS = 5
BUILD_TIMEOUT_SECONDS = 150.0
# Each query is an independent run.sh invocation and earns its own score.
# Keep the per-query budget tight enough to reject exhaustive-scan baselines
# and require a reusable low-latency index/service.
QUERY_TIMEOUT_SECONDS = 0.5
P95_TARGET_SECONDS = 0.030
MEMORY_LIMIT_BYTES = 512 * 1024 ** 2
INDEX_LIMIT_BYTES = 64 * 1024 ** 2
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
SUBMISSION_UID = 10001
SUBMISSION_GID = 10001
SUBMISSION_USER = "submission"
NOFILE_LIMIT = 1048576

SUBMISSION_COMMAND = [
    "/usr/sbin/runuser",
    "-u",
    SUBMISSION_USER,
    "--",
    # runuser resets RLIMIT_NOFILE's soft limit to 1024. Restore the same
    # explicit soft/hard limit as the development container before execution.
    "/usr/bin/prlimit",
    f"--nofile={NOFILE_LIMIT}:{NOFILE_LIMIT}",
    "--",
    "/usr/bin/setpriv",
    "--no-new-privs",
    "/usr/bin/env",
    "-i",
    f"HOME={INDEX_DIR}",
    "USER=submission",
    "LOGNAME=submission",
    "PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
    "LANG=C.UTF-8",
    "PYTHONUNBUFFERED=1",
    "PYTHONDONTWRITEBYTECODE=1",
    "TOKENIZERS_PARALLELISM=false",
    f"TMPDIR={INDEX_DIR / 'tmp'}",
    f"XDG_CACHE_HOME={INDEX_DIR / 'cache'}",
]


class VerificationError(RuntimeError):
    """Raised when verifier inputs or submission behavior are invalid."""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        handle = path.open(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot read {path}: {error}") from error
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise VerificationError(
                    f"invalid JSON in {path}:{line_number}: {error}"
                ) from error
            if not isinstance(value, dict):
                raise VerificationError(f"{path}:{line_number} is not a JSON object")
            yield value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def read_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid vector config {path}: {error}") from error
    if not isinstance(value, dict):
        raise VerificationError(f"vector config {path} is not an object")
    return value


def validate_binary(
    path: Path,
    config: dict[str, Any],
    *,
    expected_dimension: int | None = None,
) -> tuple[int, int]:
    try:
        rows = int(config["rows"])
        dimension = int(config["dimension"])
        dtype = str(config["dtype"])
    except (KeyError, TypeError, ValueError) as error:
        raise VerificationError(f"invalid vector schema in {path}: {error}") from error
    if rows <= 0 or dimension <= 0:
        raise VerificationError(f"invalid vector shape in {path}: {rows} x {dimension}")
    if dtype != "float32":
        raise VerificationError(f"{path} must use float32, got {dtype!r}")
    if expected_dimension is not None and dimension != expected_dimension:
        raise VerificationError(
            f"{path} dimension is {dimension}, expected {expected_dimension}"
        )
    expected_size = rows * dimension * VECTOR_DTYPE_BYTES
    try:
        actual_size = path.stat().st_size
    except OSError as error:
        raise VerificationError(f"cannot stat {path}: {error}") from error
    if actual_size != expected_size:
        raise VerificationError(
            f"{path} has {actual_size} bytes, expected {expected_size}"
        )
    return rows, dimension


def load_corpus_shape() -> int:
    config = read_config(TASK_DATA / "vector_config.json")
    rows, _ = validate_binary(
        TASK_DATA / "vectors.f32",
        config,
        expected_dimension=DIMENSION,
    )
    if not (TASK_DATA / "metadata.jsonl").is_file():
        raise VerificationError("corpus metadata is missing")
    return rows


def load_doc_rows(expected_rows: int) -> dict[str, int]:
    doc_rows: dict[str, int] = {}
    metadata_count = 0
    for expected_row, row in enumerate(iter_jsonl(TASK_DATA / "metadata.jsonl")):
        try:
            row_id = int(row.get("row_id", -1))
        except (TypeError, ValueError) as error:
            raise VerificationError(
                f"invalid corpus metadata row_id at row {expected_row}"
            ) from error
        if row_id != expected_row:
            raise VerificationError(
                f"corpus metadata row_id mismatch at row {expected_row}"
            )
        if "doc_id" not in row:
            raise VerificationError(f"corpus metadata row {expected_row} has no doc_id")
        doc_id = str(row["doc_id"])
        if not doc_id or doc_id in doc_rows:
            raise VerificationError(f"invalid or duplicate corpus doc_id {doc_id!r}")
        doc_rows[doc_id] = expected_row
        metadata_count += 1
    if metadata_count != expected_rows:
        raise VerificationError(
            "corpus metadata count does not match corpus vector count"
        )
    return doc_rows


def load_private_queries() -> tuple[
    list[dict[str, Any]],
    dict[str, set[str]],
    dict[str, Any],
    bytes,
]:
    query_config = read_config(PRIVATE_DATA / "vector_config.json")
    query_rows, _ = validate_binary(
        PRIVATE_DATA / "query_vectors.f32",
        query_config,
        expected_dimension=DIMENSION,
    )
    query_metadata = read_jsonl(PRIVATE_DATA / "query_metadata.jsonl")
    if query_rows != HIDDEN_QUERY_COUNT:
        raise VerificationError(
            f"expected exactly {HIDDEN_QUERY_COUNT} hidden queries, got {query_rows}"
        )
    if len(query_metadata) != query_rows:
        raise VerificationError(
            "private query metadata count does not match query vectors"
        )

    query_ids: list[str] = []
    seen_query_ids: set[str] = set()
    for expected_row, row in enumerate(query_metadata):
        try:
            row_id = int(row.get("row_id", -1))
        except (TypeError, ValueError) as error:
            raise VerificationError(
                f"invalid private query row_id at row {expected_row}"
            ) from error
        if row_id != expected_row:
            raise VerificationError(
                f"private query row_id mismatch at row {expected_row}"
            )
        query_id = str(row.get("query_id", ""))
        if not query_id or query_id in seen_query_ids:
            raise VerificationError(f"invalid or duplicate private query_id {query_id!r}")
        seen_query_ids.add(query_id)
        query_ids.append(query_id)

    ground_truth: dict[str, set[str]] = {}
    for line_number, row in enumerate(
        read_jsonl(PRIVATE_DATA / "ground_truth.jsonl"),
        start=1,
    ):
        query_id = str(row.get("query_id", ""))
        if query_id not in seen_query_ids:
            raise VerificationError(
                f"ground truth contains unknown query_id {query_id!r}"
            )
        if query_id in ground_truth:
            raise VerificationError(
                f"duplicate ground-truth query_id {query_id!r} at row {line_number}"
            )
        relevant_doc_ids = row.get("relevant_doc_ids")
        if not isinstance(relevant_doc_ids, list) or not relevant_doc_ids:
            raise VerificationError(
                f"invalid relevant_doc_ids for query {query_id!r}"
            )
        relevant = {str(doc_id) for doc_id in relevant_doc_ids}
        if len(relevant) != len(relevant_doc_ids) or "" in relevant:
            raise VerificationError(
                f"invalid or duplicate relevant doc_id for query {query_id!r}"
            )
        ground_truth[query_id] = relevant
    if set(ground_truth) != seen_query_ids:
        missing = sorted(seen_query_ids - set(ground_truth))
        raise VerificationError(f"private ground truth missing queries: {missing[:5]}")

    try:
        raw_vectors = (PRIVATE_DATA / "query_vectors.f32").read_bytes()
    except OSError as error:
        raise VerificationError(f"cannot read private query vectors: {error}") from error
    return query_metadata, ground_truth, query_config, raw_vectors


def pid_uid(pid: int) -> int | None:
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
    except OSError:
        return None
    # Zombies cannot retain mappings or create new IPC objects. Their parent
    # (possibly the verifier) may reap them after this deployment barrier.
    if any(line.startswith("State:") and line.split()[1] in ("Z", "X") for line in lines):
        return None
    for line in lines:
        if line.startswith("Uid:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def submission_pids() -> set[int]:
    result: set[int] = set()
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit() and pid_uid(int(entry.name)) == SUBMISSION_UID:
            result.add(int(entry.name))
    return result


def stop_submission_processes() -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in submission_pids():
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(0.5)
    deadline = time.monotonic() + 5.0
    while remaining := submission_pids():
        if time.monotonic() >= deadline:
            raise VerificationError("submission processes survived deployment cleanup")
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.01)


def submission_sysv_ipc() -> list[tuple[str, int]]:
    objects = []
    for kind, identifier in (("shm", "shmid"), ("msg", "msqid"), ("sem", "semid")):
        lines = Path(f"/proc/sysvipc/{kind}").read_text().splitlines()
        columns = lines[0].split()
        for line in lines[1:]:
            row = dict(zip(columns, line.split(), strict=True))
            if SUBMISSION_UID in (int(row["uid"]), int(row["cuid"])):
                objects.append((kind, int(row[identifier])))
    return objects


def clear_submission_sysv_ipc() -> None:
    flags = {"shm": "-m", "msg": "-q", "sem": "-s"}
    for kind, identifier in submission_sysv_ipc():
        # Container root need not have CAP_IPC_OWNER. Remove as the creator,
        # through a trusted binary, after every submitted process has exited.
        result = subprocess.run(
            SUBMISSION_COMMAND + ["/usr/bin/ipcrm", flags[kind], str(identifier)],
            cwd="/", capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise VerificationError(f"could not remove submission System V {kind} {identifier}")
    if submission_sysv_ipc():
        raise VerificationError("System V IPC survived deployment cleanup")


def restart_submission_for_queries() -> None:
    stop_submission_processes()
    # Build and queries share the container's private IPC namespace. System V
    # objects survive process exit and are not represented by /dev/shm files.
    clear_submission_sysv_ipc()
    for entry in Path("/dev/shm").iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.2)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_timed(
    command: list[str],
    *,
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
    output_path: Path | None = None,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    if (output_path is None) != (snapshot_path is None):
        raise ValueError("output and snapshot paths must be supplied together")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                SUBMISSION_COMMAND + command,
                cwd=SUBMISSION_DIR,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except OSError as error:
            return {
                "returncode": None,
                "elapsed_seconds": time.monotonic() - started,
                "timed_out": False,
                "error": f"could not start command: {error}",
            }

        # A blocking waitpid in a waiter thread signals a condition variable.
        # Unlike Popen.wait(timeout=...), neither wait uses timed POSIX polling.
        exited = threading.Event()
        completion = {}

        def reap():
            completion["returncode"] = process.wait()
            completion["observed"] = time.monotonic()
            exited.set()

        waiter = threading.Thread(target=reap, daemon=True)
        waiter.start()
        try:
            ready = exited.wait(max(0.0, started + timeout - time.monotonic()))
            observed = completion["observed"] if ready else time.monotonic()
            elapsed_seconds = observed - started
            process_elapsed_seconds = elapsed_seconds
            timed_out = not ready or elapsed_seconds > timeout
            output_error = None
            output_capture_seconds = 0.0
            if output_path is not None:
                if timed_out:
                    output_error = "output not captured before the query deadline"
                else:
                    capture_started = time.monotonic()
                    try:
                        freeze_output_dir(output_path.parent, output_path)
                        snapshot_completed_output(output_path, snapshot_path)
                    except (VerificationError, OSError) as error:
                        output_error = str(error)
                    captured = time.monotonic()
                    output_capture_seconds = captured - capture_started
                    # Any accepted bytes, including a retained-fd write racing
                    # with exit, must have arrived within this measured interval.
                    elapsed_seconds = captured - started
                    timed_out = elapsed_seconds > timeout
            cleanup_started = time.monotonic()
            if not ready:
                kill_group(process)
            waiter.join()
            returncode = completion["returncode"]
            cleanup_seconds = time.monotonic() - cleanup_started
        except BaseException:
            kill_group(process)
            waiter.join()
            raise
    return {
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "process_elapsed_seconds": process_elapsed_seconds,
        "output_capture_seconds": output_capture_seconds,
        "output_error": output_error,
        "timed_out": timed_out,
        "cleanup_seconds": cleanup_seconds,
    }


def resource_snapshot() -> dict[str, Any]:
    """Container-wide cgroup v2 accounting includes service and descendants."""
    root = Path("/sys/fs/cgroup")
    snapshot = {}
    for name in ("memory.max", "memory.swap.max", "memory.peak", "memory.events", "cpu.max"):
        snapshot[name] = (root / name).read_text().strip()
    return snapshot


def oom_kills(snapshot: dict[str, Any]) -> int:
    return int(dict(line.split() for line in snapshot["memory.events"].splitlines())["oom_kill"])


def summarize_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise VerificationError("no query measurements")
    latencies = []
    for row in results:
        elapsed = float(row["elapsed_seconds"])
        if not math.isfinite(elapsed) or elapsed <= 0:
            raise VerificationError("query timing must be positive and finite")
        latencies.append(QUERY_TIMEOUT_SECONDS if row.get("timed_out") or row.get("error")
                         else min(QUERY_TIMEOUT_SECONDS, elapsed))
    p95 = sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1]
    accuracy = sum(row["score"] for row in results) / len(results)
    factor = min(1.0, P95_TARGET_SECONDS / p95)
    quality_gate_passed = accuracy >= 0.95
    return {"accuracy_at_3": accuracy, "p95_seconds": p95,
            "latency_factor": factor, "minimum_accuracy_at_3": 0.95,
            "quality_gate_passed": quality_gate_passed,
            "reward_before_quality_gate": accuracy * factor,
            "reward": accuracy * factor if quality_gate_passed else 0.0}


def select_median_round(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rounds) != MEASUREMENT_ROUNDS:
        raise VerificationError("incomplete measurement rounds")
    # Stable ties use round order; accuracy never influences run selection.
    return sorted(rounds, key=lambda row: row["scoring"]["p95_seconds"])[MEASUREMENT_ROUNDS // 2]


def run_submission_check(script: str) -> bool:
    result = subprocess.run(
        SUBMISSION_COMMAND + ["/bin/sh", "-c", script],
        cwd=SUBMISSION_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def check_submission_boundary() -> None:
    script = " && ".join(
        [
            'test -z "${SILICONFLOW_API_KEY+x}"',
            'test -z "${OPENROUTER_API_KEY+x}"',
            'test -z "${JINA_API_KEY+x}"',
            'test -z "${JUDGE_API_KEY+x}"',
            'test -z "${JUDGE_MODEL_API+x}"',
            'test -z "${JUDGE_MODEL_NAME+x}"',
            'test -z "${ANSWER_JUDGE_MODEL+x}"',
            'test -z "${OPENAI_API_KEY+x}"',
            'test -z "${OPENAI_BASE_URL+x}"',
            'test -z "${TASK_1_5_JUDGE_API_KEY+x}"',
            'test -z "${CODEX_HOME+x}"',
            "test -r /task/data/vectors.f32",
            "test -r /task/data/metadata.jsonl",
            "test -r /task/data/vector_config.json",
            "test -x /app/build.sh",
            "test -x /app/run.sh",
            "test ! -r /tests/data/query_vectors.f32",
            "test ! -r /tests/data/query_metadata.jsonl",
            "test ! -r /tests/data/vector_config.json",
            "test ! -r /tests/data/ground_truth.jsonl",
            "test ! -w /logs/verifier",
        ]
    )
    if not run_submission_check(script):
        raise VerificationError(
            "submission permission or credential boundary is not configured correctly"
        )


def recreate_directory(path: Path, *, uid: int, gid: int, mode: int) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=False)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def prepare_workdirs() -> None:
    recreate_directory(WORK_DIR, uid=0, gid=0, mode=0o711)
    for root in (INPUT_ROOT, OUTPUT_ROOT):
        root.mkdir()
        os.chown(root, 0, 0)
        os.chmod(root, 0o711)
    validate_index_workspace()
    if any(INDEX_DIR.iterdir()):
        raise VerificationError("index workspace must start empty")
    os.chown(INDEX_DIR, SUBMISSION_UID, SUBMISSION_GID)
    os.chmod(INDEX_DIR, 0o750)
    for child_name in ("tmp", "cache"):
        child = INDEX_DIR / child_name
        child.mkdir()
        os.chown(child, SUBMISSION_UID, SUBMISSION_GID)
        os.chmod(child, 0o700)


def reset_measurement_workspace() -> None:
    """Discard all previous query state before another independent build."""
    restart_submission_for_queries()
    validate_index_workspace()
    for child in INDEX_DIR.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    # Keep the tmpfs mount, but remove all prior query inputs and output paths.
    prepare_workdirs()


def private_input_file(path: Path) -> None:
    os.chown(path, 0, SUBMISSION_GID)
    os.chmod(path, 0o440)


def write_single_query(
    phase: str,
    query_number: int,
    *,
    raw_vectors: bytes,
    metadata_row: dict[str, Any],
    dimension: int,
) -> tuple[Path, Path, Path, Path]:
    """Stage one private query without exposing the surrounding hidden split."""
    query_id = str(metadata_row["query_id"])
    original_row = int(metadata_row["row_id"])
    input_dir = INPUT_ROOT / f"{phase}-{query_number:03d}"
    output_dir = OUTPUT_ROOT / f"{phase}-{query_number:03d}"
    input_dir.mkdir()
    os.chown(input_dir, 0, SUBMISSION_GID)
    os.chmod(input_dir, 0o750)
    output_dir.mkdir()
    os.chown(output_dir, SUBMISSION_UID, SUBMISSION_GID)
    os.chmod(output_dir, 0o750)

    row_bytes = dimension * VECTOR_DTYPE_BYTES
    vectors_path = input_dir / "query_vectors.f32"
    start = original_row * row_bytes
    end = start + row_bytes
    vectors_path.write_bytes(raw_vectors[start:end])
    metadata_path = input_dir / "query_metadata.jsonl"
    metadata_path.write_text(
        json.dumps(
            {"row_id": 0, "query_id": query_id},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = input_dir / "vector_config.json"
    config_path.write_text(
        json.dumps(
            {
                "file": "query_vectors.f32",
                "dtype": "float32",
                "rows": 1,
                "dimension": dimension,
                "metric": "inner_product",
                "normalized": True,
                "row_order": "query_metadata.jsonl",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for path in (vectors_path, metadata_path, config_path):
        private_input_file(path)
    return vectors_path, metadata_path, config_path, output_dir / "results.jsonl"


def validate_index_workspace() -> dict[str, int]:
    # Check the real filesystem boundary, not just a declared allowance.
    if not INDEX_DIR.is_dir() or INDEX_DIR.is_symlink():
        raise VerificationError("index workspace is missing")
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    matching = [line.split() for line in mounts if line.split()[4] == str(INDEX_DIR)]
    if len(matching) != 1 or matching[0][matching[0].index("-") + 1] != "tmpfs":
        raise VerificationError("index workspace requires a dedicated tmpfs mount")
    stats = os.statvfs(INDEX_DIR)
    capacity = stats.f_blocks * stats.f_frsize
    if capacity != INDEX_LIMIT_BYTES:
        raise VerificationError("index tmpfs capacity must be exactly 64 MiB")
    return {"capacity_bytes": capacity,
            "allocated_bytes": (stats.f_blocks - stats.f_bfree) * stats.f_frsize}


def validate_query_cpu_boundary() -> dict[str, Any]:
    program = '''
import json, os
cpus = sorted(os.sched_getaffinity(0))
try:
    os.sched_setaffinity(0, cpus)
    denied_errno = 0
except OSError as error:
    denied_errno = error.errno
print(json.dumps(dict(allowed_cpus=cpus, affinity_change_errno=denied_errno)))
'''
    probe = subprocess.run(
        SUBMISSION_COMMAND + ['/usr/local/bin/search-swe-query-cpu',
                              '/opt/conda/bin/python', '-c', program],
        cwd='/', capture_output=True, text=True, timeout=10,
    )
    if probe.returncode != 0:
        raise VerificationError('query CPU launcher failed its runtime probe')
    state = json.loads(probe.stdout)
    if (state.get('allowed_cpus') != [min(os.sched_getaffinity(0))]
            or state.get('affinity_change_errno') != errno.EPERM):
        raise VerificationError('query CPU affinity boundary is not enforced')
    return state


def check_index_size(path: Path) -> int:
    size = directory_size(path)
    if size > INDEX_LIMIT_BYTES:
        raise VerificationError("index workspace logical size exceeds 64 MiB")
    return size


def directory_size(path: Path) -> int:
    total = 0
    if not path.is_dir() or path.is_symlink():
        raise VerificationError("submission index is missing or is not a real directory")
    for child in path.rglob("*"):
        if child.is_symlink():
            raise VerificationError(f"submission index contains a symlink: {child}")
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError as error:
                raise VerificationError(f"cannot stat index file {child}: {error}") from error
    return total


def freeze_output_dir(output_dir: Path, output_path: Path) -> None:
    """Restrict later path access and reject hidden side files."""
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise VerificationError(f"invalid submission output directory: {output_dir}")
    os.chown(output_dir, 0, 0)
    os.chmod(output_dir, 0o700)
    entries = list(output_dir.iterdir())
    if entries != [output_path]:
        raise VerificationError(
            f"submission output directory must contain only {output_path.name}"
        )
    if output_path.is_symlink() or not output_path.is_file():
        raise VerificationError(f"{output_path} is missing or is not a regular file")
    os.chown(output_path, 0, 0)
    os.chmod(output_path, 0o600)


def snapshot_completed_output(output_path: Path, snapshot_path: Path) -> None:
    """Bound capture size; query timing ends only after these bytes are protected."""
    with output_path.open("rb") as stream:
        content = stream.read(MAX_OUTPUT_BYTES + 1)
    if len(content) > MAX_OUTPUT_BYTES:
        raise VerificationError(f"{output_path} exceeds the output size limit")
    snapshot_path.write_bytes(content)


def validate_batch_output(
    output_path: Path,
    expected_ids: list[str],
    doc_rows: dict[str, int],
) -> list[dict[str, Any]]:
    if output_path.is_symlink() or not output_path.is_file():
        raise VerificationError(f"{output_path} is missing or is not a regular file")
    try:
        output_size = output_path.stat().st_size
    except OSError as error:
        raise VerificationError(f"cannot stat {output_path}: {error}") from error
    if output_size > MAX_OUTPUT_BYTES:
        raise VerificationError(f"{output_path} exceeds the output size limit")

    rows = read_jsonl(output_path)
    if len(rows) != len(expected_ids):
        raise VerificationError(
            f"{output_path} emitted {len(rows)} rows for {len(expected_ids)} queries"
        )

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row, expected_id in zip(rows, expected_ids):
        query_id = str(row.get("query_id", ""))
        if query_id != expected_id:
            raise VerificationError(
                f"output query_id {query_id!r} does not match expected {expected_id!r}"
            )
        if query_id in seen:
            raise VerificationError(f"duplicate output query_id {query_id!r}")
        seen.add(query_id)

        results = row.get("results")
        if not isinstance(results, list) or len(results) != TOP_K:
            raise VerificationError(
                f"query {query_id!r} must contain exactly {TOP_K} results"
            )

        result_ids: list[str] = []
        result_seen: set[str] = set()
        previous_score: float | None = None
        previous_row: int | None = None
        for item in results:
            if not isinstance(item, dict) or "doc_id" not in item or "score" not in item:
                raise VerificationError(f"invalid result item for query {query_id!r}")
            score_value = item["score"]
            if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
                raise VerificationError(f"non-numeric result score for query {query_id!r}")
            result_score = float(score_value)
            if not math.isfinite(result_score):
                raise VerificationError(f"non-finite result score for query {query_id!r}")

            doc_id = str(item["doc_id"])
            if doc_id in result_seen:
                raise VerificationError(f"duplicate result doc_id {doc_id!r}")
            if doc_id not in doc_rows:
                raise VerificationError(f"unknown result doc_id {doc_id!r}")
            corpus_row = doc_rows[doc_id]
            if previous_score is not None:
                if result_score > previous_score:
                    raise VerificationError(
                        f"results are not score-descending for query {query_id!r}"
                    )
                if result_score == previous_score and corpus_row < int(previous_row):
                    raise VerificationError(
                        f"equal-score tie-break is invalid for query {query_id!r}"
                    )
            previous_score = result_score
            previous_row = corpus_row
            result_seen.add(doc_id)
            result_ids.append(doc_id)
        normalized.append({"query_id": query_id, "results": result_ids})
    return normalized


def check_phase_metrics(metrics: dict[str, Any], label: str, *, timeout: float) -> None:
    elapsed = float(metrics.get("elapsed_seconds", math.inf))
    if metrics.get("timed_out") or not math.isfinite(elapsed) or not 0 < elapsed <= timeout:
        raise VerificationError(f"{label} exceeded its timeout")
    if metrics.get("returncode") != 0:
        raise VerificationError(f"{label} exited with {metrics.get('returncode')}")


def score_query(
    query_id: str,
    output_path: Path,
    metrics: dict[str, Any],
    output_error: str | None,
    doc_rows: dict[str, int],
    ground_truth: dict[str, set[str]],
) -> dict[str, Any]:
    """A query earns one point only when execution, latency and retrieval pass."""
    elapsed = float(metrics.get("elapsed_seconds", math.inf))
    execution_passed = metrics.get("returncode") == 0 and not metrics.get("error")
    latency_passed = (not metrics.get("timed_out") and math.isfinite(elapsed)
                      and 0 < elapsed <= QUERY_TIMEOUT_SECONDS)
    errors = []
    if not execution_passed:
        errors.append(f"run.sh exited with {metrics.get('returncode')}")
    if not latency_passed:
        errors.append(f"run.sh exceeded {QUERY_TIMEOUT_SECONDS} seconds")
    first_rank, returned_ids = None, []
    output_valid = False
    if output_error:
        errors.append(output_error)
    else:
        try:
            output = validate_batch_output(output_path, [query_id], doc_rows)[0]
            returned_ids = output["results"]
            first_rank = next((rank for rank, doc_id in enumerate(returned_ids, 1)
                               if doc_id in ground_truth[query_id]), None)
            output_valid = True
        except (VerificationError, OSError, ValueError, OverflowError, RecursionError) as error:
            errors.append(str(error))
    hit = first_rank is not None
    return {
        "query_id": query_id, **metrics,
        "execution_passed": execution_passed, "latency_passed": latency_passed,
        "output_valid": output_valid, "hit_at_3": hit,
        "first_relevant_rank": first_rank, "returned_doc_ids": returned_ids,
        "score": int(execution_passed and latency_passed and output_valid and hit),
        "errors": errors,
    }


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rounds: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "task_id": "memory-constrained-dense-retrieval", "valid": False, "score": 0.0, "reward": 0.0,
        "errors": [], "rounds": rounds,
    }
    record_batches: list[list[tuple[str, Path, dict[str, Any], str | None]]] = []
    try:
        if EXECUTION_ERROR:
            raise VerificationError(EXECUTION_ERROR)
        resources_before = resource_snapshot()
        report["resources_before"] = resources_before
        if resources_before["memory.max"] != str(MEMORY_LIMIT_BYTES) or resources_before["memory.swap.max"] != "0":
            raise VerificationError("verifier requires a 512 MiB cgroup memory limit and no swap")
        prepare_workdirs()
        check_submission_boundary()
        report['query_cpu_boundary'] = validate_query_cpu_boundary()
        corpus_rows = load_corpus_shape()
        private_metadata, ground_truth, private_config, raw_vectors = load_private_queries()
        report["query_cpu_limit"] = 1
        report["query_cpu_affinity"] = report["query_cpu_boundary"]["allowed_cpus"]
        report["query_cpu_enforcement"] = "inherited affinity; seccomp denies affinity changes"
        for round_number in range(1, MEASUREMENT_ROUNDS + 1):
            if round_number > 1:
                reset_measurement_workspace()
            round_report: dict[str, Any] = {"round": round_number}
            rounds.append(round_report)
            prefix = f"round-{round_number}"
            build_metrics = run_timed(
                [str(SUBMISSION_DIR / "build.sh"),
                 "--vectors", str(TASK_DATA / "vectors.f32"),
                 "--metadata", str(TASK_DATA / "metadata.jsonl"),
                 "--config", str(TASK_DATA / "vector_config.json"),
                 "--index-dir", str(INDEX_DIR)],
                timeout=BUILD_TIMEOUT_SECONDS,
                stdout_path=RESULTS_DIR / f"{prefix}.build.stdout.log",
                stderr_path=RESULTS_DIR / f"{prefix}.build.stderr.log",
            )
            round_report["build"] = build_metrics
            check_phase_metrics(build_metrics, f"round {round_number} build.sh", timeout=BUILD_TIMEOUT_SECONDS)
            index_bytes_after_build = check_index_size(INDEX_DIR)
            round_report["index_workspace_after_build"] = validate_index_workspace()
            round_report["index_bytes_after_build"] = index_bytes_after_build
            if index_bytes_after_build <= 0:
                raise VerificationError("build.sh did not create a persistent index")

            # Each run starts from persisted state, without a build-started service.
            restart_submission_for_queries()
            round_report["service_restart_before_queries"] = True
            records: list[tuple[str, Path, dict[str, Any], str | None]] = []
            for query_number, metadata_row in enumerate(private_metadata, start=1):
                vectors_path, metadata_path, config_path, output_path = write_single_query(
                    prefix, query_number, raw_vectors=raw_vectors,
                    metadata_row=metadata_row, dimension=int(private_config["dimension"]),
                )
                snapshot_path = RESULTS_DIR / f"{prefix}.query-{query_number:03d}.results.jsonl"
                metrics = run_timed(
                    ["/usr/local/bin/search-swe-query-cpu", str(SUBMISSION_DIR / "run.sh"), "--index-dir", str(INDEX_DIR),
                     "--query-vectors", str(vectors_path),
                     "--query-metadata", str(metadata_path),
                     "--query-config", str(config_path),
                     "--output", str(output_path), "--top-k", str(TOP_K)],
                    timeout=QUERY_TIMEOUT_SECONDS,
                    stdout_path=RESULTS_DIR / f"{prefix}.query-{query_number:03d}.stdout.log",
                    stderr_path=RESULTS_DIR / f"{prefix}.query-{query_number:03d}.stderr.log",
                    output_path=output_path,
                    snapshot_path=snapshot_path,
                )
                output_error = metrics.get("output_error")
                records.append((str(metadata_row["query_id"]), snapshot_path, metrics, output_error))
                check_index_size(INDEX_DIR)
            stop_submission_processes()
            round_report["index_bytes"] = check_index_size(INDEX_DIR)
            round_report["index_workspace_final"] = validate_index_workspace()
            record_batches.append(records)

        # Load the large corpus lookup only after all timed workloads and IPC end.
        restart_submission_for_queries()
        doc_rows = load_doc_rows(corpus_rows)
        for query_id, relevant in ground_truth.items():
            unknown = relevant - doc_rows.keys()
            if unknown:
                raise VerificationError(f"ground truth for {query_id!r} contains unknown document IDs")
        for round_report, records in zip(rounds, record_batches, strict=True):
            results = [score_query(query_id, path, metrics, error, doc_rows, ground_truth)
                       for query_id, path, metrics, error in records]
            round_report["queries"] = results
            round_report["scoring"] = summarize_scores(results)
        selected = select_median_round(rounds)
        results = selected["queries"]
        passed = sum(row["score"] for row in results)
        aggregate = selected["scoring"]
        metric = aggregate["accuracy_at_3"]
        report["resources_after"] = resource_snapshot()
        if oom_kills(report["resources_after"]) > oom_kills(resources_before):
            raise VerificationError("container memory limit caused an OOM kill")
        report.update({
            "valid": True, "score": 100.0 * aggregate["reward"], "reward": aggregate["reward"],
            "selected_round": selected["round"],
            "build": selected["build"],
            "service_restart_before_queries": selected["service_restart_before_queries"],
            "index_bytes_after_build": selected["index_bytes_after_build"],
            "index_workspace_after_build": selected["index_workspace_after_build"],
            "index_bytes": selected["index_bytes"],
            "index_workspace_final": selected["index_workspace_final"],
            "scoring": {**aggregate, "p95_target_seconds": P95_TARGET_SECONDS,
                        "timing_end": "protected output capture after client exit",
                        "quantile": "nearest-rank ceil(0.95*N), one-based",
                        "rounds": MEASUREMENT_ROUNDS,
                        "selection": "median round P95; accuracy from the same round; ties by round order",
                        "selected_round": selected["round"],
                        "round_p95_seconds": [row["scoring"]["p95_seconds"] for row in rounds],
                        "timeout_latency_seconds": QUERY_TIMEOUT_SECONDS},
            "query_count": len(results), "passed_queries": passed,
            "all_cases_passed": passed == HIDDEN_QUERY_COUNT,
            "primary_metric": {
                "name": "Accuracy@3", "value": metric, "query_count": len(results),
                "latency_limit_seconds": QUERY_TIMEOUT_SECONDS,
                "per_query_latency_gate": True, "all_queries_required": False,
            },
            "diagnostic_metrics": {
                "raw_accuracy_at_3": sum(r["hit_at_3"] for r in results) / HIDDEN_QUERY_COUNT,
                "latency_passed_queries": sum(r["latency_passed"] for r in results),
                "query_errors": sum(bool(r["errors"]) for r in results),
                "sum_run_seconds": sum(r["elapsed_seconds"] for r in results),
                "max_query_seconds": max(r["elapsed_seconds"] for r in results),
            },
            "queries": results,
        })
    except Exception as error:
        report["errors"].append(str(error))
    finally:
        try:
            stop_submission_processes()
        except Exception as error:
            report.update(valid=False, score=0.0, reward=0.0)
            report["errors"].append(f"cannot confirm submission cleanup: {error}")
        try:
            report["resources_final"] = resource_snapshot()
        except OSError as error:
            report["errors"].append(f"cannot record final cgroup resources: {error}")

    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
