#!/usr/bin/env python3
"""Private verifier for Task-1-2's memory-constrained vector retrieval."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


TASK_DATA = Path("/task/data")
PRIVATE_DATA = Path("/tests/data")
SUBMISSION_DIR = Path("/app")
WORK_DIR = Path("/tmp/task-1-2-eval")
INPUT_ROOT = WORK_DIR / "input"
INDEX_DIR = WORK_DIR / "index"
OUTPUT_ROOT = WORK_DIR / "output"
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/task-1-2-eval")
)
REPORT_PATH = RESULTS_DIR / "evaluation.json"
EXECUTION_ERROR = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")

DIMENSION = 1024
VECTOR_DTYPE_BYTES = 4
TOP_K = 3
QUALITY_K = 3
QUALITY_QUERY_IDS = (
    "test461",
    "test1329",
    "test2849",
    "test595",
    "test1503",
)
QUALITY_QUERY_ID_SET = frozenset(QUALITY_QUERY_IDS)
PERFORMANCE_QUERY_COUNT = 50
BUILD_TIMEOUT_SECONDS = 120.0
# Each quality and performance query is an independent run.sh invocation.
# Keep the per-query budget tight enough to reject exhaustive-scan baselines
# and require a reusable low-latency index/service.
QUERY_TIMEOUT_SECONDS = 0.5
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
SUBMISSION_UID = 10001
SUBMISSION_GID = 10001
SUBMISSION_USER = "submission"

SUBMISSION_COMMAND = [
    "/usr/sbin/runuser",
    "-u",
    SUBMISSION_USER,
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
) -> dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
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

        timed_out = False
        try:
            # wait() returns as soon as the child exits, avoiding the coarse
            # polling window that could otherwise accept a late process.
            remaining = max(0.0, started + timeout - time.monotonic())
            returncode = process.wait(timeout=remaining)
            finished_at = time.monotonic()
        except subprocess.TimeoutExpired:
            # The timeout boundary can race with process exit. Recheck before
            # killing the process, then judge the observed completion time.
            returncode = process.poll()
            if returncode is None:
                timed_out = True
                kill_group(process)
                stop_submission_processes()
                try:
                    returncode = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    returncode = None
            finished_at = time.monotonic()

        elapsed_seconds = finished_at - started
        if elapsed_seconds > timeout:
            timed_out = True
    return {
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "timed_out": timed_out,
    }


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
    INDEX_DIR.mkdir()
    os.chown(INDEX_DIR, SUBMISSION_UID, SUBMISSION_GID)
    os.chmod(INDEX_DIR, 0o750)
    for child_name in ("tmp", "cache"):
        child = INDEX_DIR / child_name
        child.mkdir()
        os.chown(child, SUBMISSION_UID, SUBMISSION_GID)
        os.chmod(child, 0o700)


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
    """Block later submission writes and reject hidden side files."""
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


def score(
    results: list[dict[str, Any]],
    ground_truth: dict[str, set[str]],
    *,
    cutoff: int = TOP_K,
) -> tuple[float, float]:
    if cutoff <= 0 or cutoff > TOP_K:
        raise ValueError(f"invalid scoring cutoff: {cutoff}")
    hits = 0
    reciprocal_rank = 0.0
    for row in results:
        relevant = ground_truth[row["query_id"]]
        for rank, doc_id in enumerate(row["results"][:cutoff], start=1):
            if doc_id in relevant:
                hits += 1
                reciprocal_rank += 1.0 / rank
                break
    count = len(results)
    return hits / count, reciprocal_rank / count


def check_phase_metrics(metrics: dict[str, Any], label: str) -> None:
    if metrics.get("timed_out"):
        raise VerificationError(f"{label} exceeded its timeout")
    if metrics.get("returncode") != 0:
        raise VerificationError(f"{label} exited with {metrics.get('returncode')}")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "task_id": "task-1-2",
        "valid": False,
        "score": 0.0,
        "errors": [],
    }
    quality_records: list[tuple[Path, list[str]]] = []
    performance_records: list[tuple[Path, list[str]]] = []
    quality_metrics: list[dict[str, Any]] = []
    performance_metrics: list[dict[str, Any]] = []
    try:
        if EXECUTION_ERROR:
            raise VerificationError(EXECUTION_ERROR)
        prepare_workdirs()
        check_submission_boundary()
        corpus_rows = load_corpus_shape()
        private_metadata, ground_truth, private_config, raw_vectors = (
            load_private_queries()
        )

        build_metrics = run_timed(
            [
                str(SUBMISSION_DIR / "build.sh"),
                "--vectors",
                str(TASK_DATA / "vectors.f32"),
                "--metadata",
                str(TASK_DATA / "metadata.jsonl"),
                "--config",
                str(TASK_DATA / "vector_config.json"),
                "--index-dir",
                str(INDEX_DIR),
            ],
            timeout=BUILD_TIMEOUT_SECONDS,
            stdout_path=RESULTS_DIR / "build.stdout.log",
            stderr_path=RESULTS_DIR / "build.stderr.log",
        )
        report["build"] = build_metrics
        check_phase_metrics(build_metrics, "build.sh")
        if not INDEX_DIR.is_dir() or INDEX_DIR.is_symlink():
            raise VerificationError("build.sh did not create a persistent index")
        index_bytes_after_build = directory_size(INDEX_DIR)
        report["index_bytes_after_build"] = index_bytes_after_build
        if index_bytes_after_build <= 0:
            raise VerificationError("build.sh did not create a persistent index")

        metadata_by_id = {
            str(row["query_id"]): row for row in private_metadata
        }
        missing_quality = [
            query_id
            for query_id in QUALITY_QUERY_IDS
            if query_id not in metadata_by_id
        ]
        if missing_quality:
            raise VerificationError(
                f"quality sentinel queries are missing: {missing_quality}"
            )
        quality_metadata = [metadata_by_id[query_id] for query_id in QUALITY_QUERY_IDS]
        remaining_metadata = [
            row for row in private_metadata
            if str(row["query_id"]) not in QUALITY_QUERY_ID_SET
        ]
        if len(remaining_metadata) < PERFORMANCE_QUERY_COUNT:
            raise VerificationError("not enough private queries for the performance set")
        performance_metadata = [
            remaining_metadata[(index * len(remaining_metadata)) // PERFORMANCE_QUERY_COUNT]
            for index in range(PERFORMANCE_QUERY_COUNT)
        ]

        def run_one_query(
            phase: str,
            query_number: int,
            metadata_row: dict[str, Any],
        ) -> tuple[Path, list[str], dict[str, Any]]:
            vectors_path, metadata_path, config_path, output_path = write_single_query(
                phase,
                query_number,
                raw_vectors=raw_vectors,
                metadata_row=metadata_row,
                dimension=int(private_config["dimension"]),
            )
            metrics = run_timed(
                [
                    str(SUBMISSION_DIR / "run.sh"),
                    "--index-dir",
                    str(INDEX_DIR),
                    "--query-vectors",
                    str(vectors_path),
                    "--query-metadata",
                    str(metadata_path),
                    "--query-config",
                    str(config_path),
                    "--output",
                    str(output_path),
                    "--top-k",
                    str(TOP_K),
                ],
                timeout=QUERY_TIMEOUT_SECONDS,
                stdout_path=RESULTS_DIR / f"run.{phase}-{query_number:03d}.stdout.log",
                stderr_path=RESULTS_DIR / f"run.{phase}-{query_number:03d}.stderr.log",
            )
            check_phase_metrics(metrics, f"run.sh on {phase}-{query_number:03d}")
            freeze_output_dir(output_path.parent, output_path)
            return output_path, [str(metadata_row["query_id"])], metrics

        for query_number, metadata_row in enumerate(quality_metadata, start=1):
            output_path, expected_ids, metrics = run_one_query(
                "quality", query_number, metadata_row
            )
            quality_records.append((output_path, expected_ids))
            quality_metrics.append(metrics)

        for query_number, metadata_row in enumerate(performance_metadata, start=1):
            output_path, expected_ids, metrics = run_one_query(
                "performance", query_number, metadata_row
            )
            performance_records.append((output_path, expected_ids))
            performance_metrics.append(metrics)

        # A build-started service may remain alive across all single-query calls.
        # Terminate every submission process before root reads untrusted output.
        stop_submission_processes()

        index_bytes = directory_size(INDEX_DIR)
        report["index_bytes"] = index_bytes

        doc_rows = load_doc_rows(corpus_rows)
        for query_id, relevant in ground_truth.items():
            unknown_doc_ids = sorted(relevant - doc_rows.keys())
            if unknown_doc_ids:
                raise VerificationError(
                    f"ground truth for {query_id!r} contains unknown doc_id "
                    f"{unknown_doc_ids[0]!r}"
                )

        quality_results: list[dict[str, Any]] = []
        for output_path, expected_ids in quality_records:
            quality_results.extend(
                validate_batch_output(output_path, expected_ids, doc_rows)
            )
        performance_results: list[dict[str, Any]] = []
        for output_path, expected_ids in performance_records:
            performance_results.extend(
                validate_batch_output(output_path, expected_ids, doc_rows)
            )

        expected_quality_order = list(QUALITY_QUERY_IDS)
        if [row["query_id"] for row in quality_results] != expected_quality_order:
            raise VerificationError(
                "quality output query order does not match the sentinel order"
            )
        expected_performance_order = [
            str(row["query_id"]) for row in performance_metadata
        ]
        if [row["query_id"] for row in performance_results] != expected_performance_order:
            raise VerificationError(
                "performance output query order does not match the private workload"
            )

        quality_accuracy, quality_mrr = score(
            quality_results, ground_truth, cutoff=QUALITY_K
        )
        if quality_accuracy < 1.0:
            raise VerificationError(
                "quality sentinel gate failed: all five queries must hit a "
                "relevant document in the top three results"
            )

        performance_run_seconds = sum(
            float(item["elapsed_seconds"]) for item in performance_metrics
        )
        performance_max = max(
            (float(item["elapsed_seconds"]) for item in performance_metrics),
            default=0.0,
        )
        report["valid"] = True
        report["score"] = 100.0 * quality_accuracy
        report["query_count"] = len(quality_results) + len(performance_results)
        report["primary_metric"] = {
            "name": "Accuracy@3",
            "value": quality_accuracy,
            "query_count": len(quality_results),
            "all_queries_required": True,
        }
        report["diagnostic_metrics"] = {
            "mrr_at_3": quality_mrr,
            "quality_query_count": len(quality_results),
            "performance_query_count": len(performance_results),
            "performance_sum_run_seconds": performance_run_seconds,
            "performance_max_query_seconds": performance_max,
        }
        report["quality_queries"] = quality_metrics
        report["performance_queries"] = performance_metrics
    except Exception as error:
        report["errors"].append(str(error))
    finally:
        stop_submission_processes()

    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
