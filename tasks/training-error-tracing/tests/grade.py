"""Execution supervisor for packaged inputs and unprivileged submissions.

Real requests, synthetic boundary fixtures and paired efficiency phases share
the same resource, timeout, output-validation and process-cleanup controls.
"""

import argparse
import ctypes
import csv
import hashlib
import json
import os
import random
import signal
import stat
from statistics import median, quantiles
import subprocess
import threading
import time
from pathlib import Path

from metrics import macro_precision, normalized_score, query_precision
from storage_accounting import inventory, total_bytes, require_inspection_capabilities

UID = GID = 10001
MAX_OUTPUT_BYTES = 65536
MAX_LOG_BYTES = 262144


def verify_runtime_limits():
    """Reject an incorrectly provisioned verifier instead of scoring its solver."""
    cgroup = Path("/sys/fs/cgroup")
    quota, period = (cgroup / "cpu.max").read_text().split()
    if quota == "max" or int(quota)/int(period) != 16:
        raise ValueError("Verifier must enforce exactly 16 CPU cores of quota")
    memory = (cgroup / "memory.max").read_text().strip()
    swap = (cgroup / "memory.swap.max").read_text().strip()
    if memory == "max" or int(memory) != 16*1024**3 or swap != "0":
        raise ValueError("Verifier must enforce 16 GiB RAM and no swap")
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid,name,memory.total",
                                   "--format=csv,noheader,nounits"], text=True, timeout=10)
    rows = list(csv.reader(raw.splitlines()))
    if len(rows) != 1 or len(rows[0]) != 3:
        raise ValueError("Verifier must expose exactly one physical GPU")
    uuid, name, total = [value.strip() for value in rows[0]]
    if not uuid.startswith("GPU-") or "A100" not in name or "40GB" not in name or not 39000 <= int(total) <= 42000:
        raise ValueError("Verifier requires one physical A100 40GB")
    return {"cpu_quota_cores": 16, "memory_max_bytes": int(memory), "memory_swap_max_bytes": 0,
            "gpu_uuid": uuid, "gpu_name": name, "gpu_memory_total_mib": int(total),
            "storage_enforcement": "logical-byte audit; not a kernel filesystem quota"}


class InvalidSubmission(Exception):
    pass


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


def tree_size(roots):
    return sum(inventory(roots).values())


def user_processes():
    found = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            status = (path / "status").read_text()
            uid = next(line.split()[1] for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid) == UID:
                birth = (path / "stat").read_text().rsplit(") ", 1)[1].split()[19]
                found[int(path.name)] = birth
        except (OSError, StopIteration, IndexError):
            continue
    return found


def kill_new_processes(before):
    # Preserve preparation-started services. Kill new detached helpers as well
    # as the foreground process group; setsid must not bypass the query budget.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, birth in user_processes().items():
            if before.get(pid) == birth:
                continue
            try:
                os.kill(pid, sig)
                if sig == signal.SIGTERM:
                    os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(.05)
    deadline = time.monotonic()+1
    while True:
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
            except ChildProcessError:
                break
        remaining = {pid: birth for pid, birth in user_processes().items()
                     if before.get(pid) != birth}
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(.01)


def signal_services(processes, sig):
    current = user_processes()
    for pid, birth in processes.items():
        if current.get(pid) != birth:
            continue
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def lock_submission(root):
    if not root.is_dir() or root.is_symlink():
        raise InvalidSubmission("Missing submission directory")
    for path in [*root.rglob("*"), root]:
        if path.is_symlink():
            continue
        info = path.stat()
        os.chown(path, 0, 0)
        os.chmod(path, 0o555 if path.is_dir() or info.st_mode & 0o111 else 0o444)
    for name in ("prepare.sh", "run.sh"):
        path = root / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise InvalidSubmission("Missing executable " + name)


def validate_submission_metadata(root):
    try:
        path = root / "submission.json"
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024**2:
                raise ValueError("Invalid metadata file")
            metadata = json.loads(os.read(fd, 1024**2+1))
        finally:
            os.close(fd)
        if (not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int
                or metadata["schema_version"] != 1
                or not isinstance(metadata.get("method"), str) or not metadata["method"].strip()
                or not isinstance(metadata.get("configuration"), dict)
                or not isinstance(metadata.get("frozen_artifacts"), list)):
            raise ValueError("Invalid metadata schema")
        seen = set()
        for artifact in metadata["frozen_artifacts"]:
            name = artifact["path"]
            if not isinstance(name, str) or name in seen:
                raise ValueError("Invalid or duplicate artifact path")
            seen.add(name)
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Artifact must be inside submission")
            path = root / relative
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError("Artifact link escapes submission")
            if not path.is_file() or not isinstance(artifact.get("generation"), str) or not artifact["generation"].strip():
                raise ValueError("Missing artifact or generation configuration")
            with path.open("rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if artifact.get("sha256") != actual_hash:
                raise ValueError("Frozen artifact checksum mismatch")
        return metadata
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise InvalidSubmission("Invalid submission.json or frozen artifact metadata") from error


def verify_public_readability(roots, *, write_paths=(), context="Public task inputs"):
    # Check as the actual candidate UID. Root readability would hide a broken
    # public bind mount and misreport a preparation error as solver failure.
    code = """import json,os,sys
from pathlib import Path
write_paths=set(json.loads(sys.argv[1]))
for name in sys.argv[2:]:
 root=Path(name)
 required=os.R_OK|os.X_OK|(os.W_OK if name in write_paths else 0)
 if not root.is_dir() or not os.access(root,required):raise PermissionError(name)
 for directory,subdirs,files in os.walk(root,onerror=lambda error:(_ for _ in ()).throw(error)):
  for entry in subdirs+files:
   path=Path(directory)/entry
   mode=os.R_OK|(os.X_OK if path.is_dir() else 0)
   if not os.access(path,mode):raise PermissionError(str(path))
"""
    check = subprocess.run(["/usr/bin/setpriv", f"--reuid={UID}", f"--regid={GID}",
                            "--clear-groups", "--no-new-privs", "/opt/conda/bin/python", "-c", code,
                            json.dumps([str(path) for path in write_paths]),
                            *[str(root) for root in roots]],
                           env={"PATH": "/opt/conda/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                           capture_output=True, text=True, timeout=10)
    if check.returncode:
        raise ValueError(context+" are not accessible by the candidate UID: "+check.stderr[-1000:])


def candidate_environment(index):
    result = {"PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(index / "home"),
              "USER": "submission", "LOGNAME": "submission", "LANG": "C.UTF-8",
              "TMPDIR": str(index / "tmp"), "XDG_CACHE_HOME": str(index / "cache"),
              "HF_HOME": str(index / "hf"), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
              "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
              "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "16"}
    # CUDA runtime paths contain no judge or coding-model credentials.
    for key in ("LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES"):
        if os.environ.get(key):
            result[key] = os.environ[key]
    return result


def bounded_log(pipe, path):
    with path.open("wb") as target:
        written = 0
        while block := pipe.read(65536):
            keep = min(len(block), MAX_LOG_BYTES-written)
            if keep > 0:
                target.write(block[:keep])
                target.flush()
                written += keep
    pipe.close()


def memory_oom_count():
    path = Path("/sys/fs/cgroup/memory.events")
    if not path.exists():
        return 0
    return int(dict(line.split() for line in path.read_text().splitlines()).get("oom_kill", 0))


def run_command(command, *, cwd, index, timeout, log, storage_roots, fixed_files, budget):
    started = time.monotonic()
    before = user_processes()
    initial_oom = memory_oom_count()
    fixed_bytes = sum(fixed_files.values())
    environment = candidate_environment(index)
    argv = ["/usr/bin/setpriv", f"--reuid={UID}", f"--regid={GID}", "--clear-groups",
            "--no-new-privs", "--inh-caps=-all", "--ambient-caps=-all", "--bounding-set=-all",
            "/usr/bin/env", "-i", *[f"{k}={v}" for k, v in environment.items()], *command]
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    logger = threading.Thread(target=bounded_log, args=(process.stdout, log), daemon=True)
    logger.start()
    finished = threading.Event()
    finished_at = None
    def reap():
        nonlocal finished_at
        process.wait()
        # Persistent preparation services must not compute during final audits.
        signal_services(user_processes(), signal.SIGSTOP)
        # Resource audits can outlast a short request. Record command completion
        # in its waiter so the verifier's audit work is not query computation.
        finished_at = time.monotonic()
        finished.set()
    waiter = threading.Thread(target=reap, daemon=True)
    waiter.start()
    timed_out, resource_violation = False, False
    next_storage_check = started
    peak_storage = fixed_bytes
    while not finished.is_set():
        now = time.monotonic()
        if now >= next_storage_check:
            peak_storage = max(peak_storage, total_bytes(storage_roots, fixed_files))
            next_storage_check = now + .5
        if peak_storage > budget or memory_oom_count() > initial_oom:
            resource_violation = True
            break
        if now - started >= timeout:
            timed_out = True
            break
        finished.wait(timeout=min(.05, max(.001, timeout-(now-started))))
    ended = finished_at if finished_at is not None else time.monotonic()
    timed_out |= ended-started > timeout
    if timed_out or resource_violation:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        kill_new_processes(before)
        process.wait(timeout=5)
    waiter.join(timeout=.02)
    logger.join(timeout=.02)
    peak_storage = max(peak_storage, total_bytes(storage_roots, fixed_files))
    resource_violation |= peak_storage > budget or memory_oom_count() > initial_oom
    return {"returncode": process.returncode, "elapsed_sec": ended-started,
            "timed_out": timed_out, "resource_violation": resource_violation,
            "oom_kill_events": max(0, memory_oom_count()-initial_oom),
            "peak_observed_storage_bytes": peak_storage, "processes_before": before}


def read_output(path, query_id):
    # Output directories are under a root-owned parent. O_NOFOLLOW prevents
    # the candidate from making the root grader open a hidden-file symlink.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OUTPUT_BYTES:
            raise ValueError("Invalid output file")
        data = os.read(fd, MAX_OUTPUT_BYTES+1)
        if len(data) > MAX_OUTPUT_BYTES:
            raise ValueError("Oversized output")
    finally:
        os.close(fd)
    result = json.loads(data)
    if not isinstance(result, dict) or result.get("query_id") != query_id:
        raise ValueError("Wrong query ID")
    return result.get("ids")


def main(phase_args=None, phase_config=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission", type=Path, default=Path("/app/submission"))
    parser.add_argument("--data", type=Path, default=Path("/task/data"))
    parser.add_argument("--models", type=Path, default=Path("/task/models"))
    parser.add_argument("--private", type=Path, default=Path("/tests/data"))
    parser.add_argument("--work", type=Path, default=Path("/work/tracing"))
    parser.add_argument("--logs", type=Path, default=Path("/logs/verifier"))
    args = phase_args if phase_args is not None else parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError("Supervisor must be root; candidates always run as UID10001")
    args.logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.logs.chmod(0o700)
    (args.logs / "reward.txt").write_text("0\n")
    report = {"valid_task_inputs": False, "submission_valid": False, "reward": 0.0,
              "infrastructure_error": False, "queries": []}
    memory_tracker = None
    try:
        require_inspection_capabilities()
        config = phase_config if phase_config is not None else json.loads((args.private / "evaluation-config.json").read_text())
        if not config.get("raw_efficiency_phase"):
            normalized_score(0, config["B"], config["U"])
        if not (config.get("synthetic_fixture_only") or config.get("synthetic_interface_fixture_only")):
            report["runtime_profile"] = verify_runtime_limits()
        valid_ids = {json.loads(line)["id"] for line in (args.data / "train.jsonl").read_text().splitlines()}
        queries = [json.loads(line) for line in (args.private / "queries.jsonl").read_text().splitlines()]
        groups = json.loads((args.private / "labels.json").read_text())
        qgroups = {}
        relevant = {}
        seen_records = set()
        for gid, group in groups.items():
            relevant[gid] = set(group["record_ids"])
            if len(relevant[gid]) < 10 or not relevant[gid] <= valid_ids:
                raise ValueError("Invalid private contamination set")
            if seen_records & relevant[gid]:
                raise ValueError("Private contamination groups overlap")
            seen_records.update(relevant[gid])
            if len(group["query_ids"]) < config["minimum_queries_per_group"]:
                raise ValueError("Too few actual errors in a private group")
            for qid in group["query_ids"]:
                if qid in qgroups:
                    raise ValueError("Overlapping private query groups")
                qgroups[qid] = gid
        if len(queries) != config["query_count"] or len(groups) != config["group_count"]:
            raise ValueError("Private query/group count mismatch")
        if len(set(q["id"] for q in queries)) != len(queries) or set(qgroups) != {q["id"] for q in queries}:
            raise ValueError("Private queries and labels do not align")
        for query in queries:
            tokens = query["input_ids"]
            positions = query["target_token_indices"]
            prompt_count = query["prompt_token_count"]
            if (not isinstance(tokens, list) or not 1 < len(tokens) <= 512
                    or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in tokens)
                    or isinstance(prompt_count, bool) or not isinstance(prompt_count, int)
                    or not 0 <= prompt_count < len(tokens)
                    or not isinstance(positions, list) or not positions
                    or any(isinstance(i, bool) or not isinstance(i, int)
                           or not max(1, prompt_count) <= i < len(tokens) for i in positions)
                    or len(set(positions)) != len(positions)):
                raise ValueError("Invalid frozen query tokens or target positions")
        report["valid_task_inputs"] = True
        public_roots = [args.data, args.models]
        if Path("/task/tools").exists():
            public_roots.append(Path("/task/tools"))
        verify_public_readability(public_roots)
        lock_submission(args.submission)
        validate_submission_metadata(args.submission)
        fixed_files = inventory([args.data, args.models, args.submission])
        fixed_bytes = sum(fixed_files.values())
        if fixed_bytes > config["storage_bytes"]:
            raise InvalidSubmission("Fixed inputs and submission exceed total storage budget")
        args.work.mkdir(parents=True, mode=0o711)
        args.work.chmod(0o711)
        index, inputs, outputs = [args.work / name for name in ("index", "input", "output")]
        for path in (index, outputs):
            path.mkdir(mode=0o700)
            os.chown(path, UID, GID)
        inputs.mkdir(mode=0o750)
        os.chown(inputs, 0, GID)
        for name in ("home", "tmp", "cache", "hf"):
            path = index / name
            path.mkdir(mode=0o700)
            os.chown(path, UID, GID)
        verify_public_readability([index, inputs, outputs], write_paths=[index, outputs],
                                  context="Verifier workspace directories")
        if config.get("measure_gpu_memory"):
            from gpu_memory import GPUMemoryPeak
            memory_tracker = GPUMemoryPeak(report["runtime_profile"]["gpu_uuid"])
            memory_tracker.start()
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
        storage_roots = [args.work, Path("/dev/shm"), Path("/tmp"), Path("/var/tmp"),
                         Path("/run/lock"), Path("/home/submission")]
        prepare = run_command([str(args.submission / "prepare.sh"), "--data-dir", str(args.data),
                               "--model-dir", str(args.models), "--index-dir", str(index)],
                              cwd=args.submission, index=index, timeout=config["prepare_timeout_sec"],
                              log=args.logs / "prepare.log", storage_roots=storage_roots,
                              fixed_files=fixed_files, budget=config["storage_bytes"])
        report["prepare"] = {k: v for k, v in prepare.items() if k != "processes_before"}
        if prepare["returncode"] != 0 or prepare["timed_out"] or prepare["resource_violation"]:
            raise InvalidSubmission("Preparation failed, timed out or exceeded total resources")
        # Services get preparation time and the current request's time, with
        # no background computation allowance between requests.
        signal_services(user_processes(), signal.SIGSTOP)
        report["passes"] = []
        repetitions = config.get("repetitions", 1)
        if type(repetitions) is not int or not 1 <= repetitions <= 3:
            raise ValueError("Invalid query repetition count")
        for repetition in range(repetitions):
            query_results = {}
            ordered = list(queries)
            if repetitions > 1:
                random.Random(config["query_order_seed"]+repetition).shuffle(ordered)
            for number, query in enumerate(ordered):
                before = user_processes()
                query_start = time.monotonic()
                query_path = inputs / f"query-{repetition:02d}-{number:04d}.json"
                query_path.write_text(json.dumps(query)+"\n")
                os.chown(query_path, 0, GID)
                query_path.chmod(0o440)
                output = outputs / f"result-{repetition:02d}-{number:04d}.json"
                signal_services(before, signal.SIGCONT)
                command_start = time.monotonic()
                run = run_command([str(args.submission / "run.sh"), "--index-dir", str(index),
                                   "--query", str(query_path), "--output", str(output), "--top-k", "10"],
                                  cwd=args.submission, index=index,
                                  timeout=max(.001, config["query_timeout_sec"]-(time.monotonic()-query_start)),
                                  log=args.logs / f"query-{repetition:02d}-{number:04d}.log", storage_roots=storage_roots,
                                  fixed_files=fixed_files, budget=config["storage_bytes"])
                ids, reason = [], None
                if run["returncode"] == 0 and not run["timed_out"]:
                    try:
                        ids = read_output(output, query["id"])
                    except (OSError, ValueError, TypeError):
                        reason = "missing-or-malformed-output"
                else:
                    reason = "timeout" if run["timed_out"] else "command-failed"
                # Delivery/startup and command execution count; a post-completion
                # resource scan does not add synthetic query latency.
                elapsed = command_start-query_start+run["elapsed_sec"]
                signal_services(before, signal.SIGSTOP)
                if reason is not None:
                    ids = []
                query_results[query["id"]] = {"ids": ids, "elapsed_sec": elapsed}
                precision = query_precision(ids, relevant[qgroups[query["id"]]], valid_ids,
                                              elapsed, config["query_timeout_sec"])
                report["queries"].append({"id": query["id"], "group_id": qgroups[query["id"]],
                                           "repetition": repetition, "elapsed_sec": elapsed, "execution_error": reason,
                                           **precision, "returned_ids": ids[:11] if isinstance(ids, list) else [],
                                           **{k: v for k, v in run.items() if k not in {"processes_before", "elapsed_sec"}}})
                kill_new_processes(before)
                query_path.unlink()
                output.unlink(missing_ok=True)
                if run["resource_violation"]:
                    raise InvalidSubmission("Total resource budget exceeded during query")
            scores = macro_precision([{"id": q["id"], "group_id": qgroups[q["id"]]} for q in queries],
                                     query_results, relevant, valid_ids, config["query_timeout_sec"])
            report["passes"].append(scores)
        report.update(submission_valid=True, Q=min(row["Q"] for row in report["passes"]),
                      p5=min(row["p5"] for row in report["passes"]), groups=scores["groups"])
        if config.get("raw_efficiency_phase"):
            report.update(raw_efficiency_phase=True, reward=0.0)
        else:
            report.update(B=config["B"], U=config["U"],
                          reward=normalized_score(report["Q"], config["B"], config["U"])/100)
        timings = [q["elapsed_sec"] for q in report["queries"]]
        report["query_latency"] = {"p50_sec": median(timings),
                                   "p95_sec": quantiles(timings, n=100, method="inclusive")[94] if len(timings)>1 else timings[0],
                                   "max_sec": max(timings)}
    except InvalidSubmission as error:
        report["submission_error"] = str(error)
    except Exception as error:
        report.update(infrastructure_error=True, infrastructure_exception=type(error).__name__,
                      infrastructure_message=str(error))
    finally:
        kill_new_processes({})
        if memory_tracker is not None:
            try:
                report["gpu_memory"] = memory_tracker.finish()
            except Exception as error:
                report.update(infrastructure_error=True, reward=0.0,
                              infrastructure_exception=type(error).__name__, infrastructure_message=str(error))
        for name in ("memory.peak", "cpu.stat", "memory.events"):
            path = Path("/sys/fs/cgroup") / name
            if path.is_file():
                report.setdefault("container_cgroup", {})[name] = path.read_text().strip()
        write_json(args.logs / "evaluation.json", report)
    # An independent integrity judge must accept the trajectory before a
    # production finalizer can turn this intermediate result into a reward.
    return 1 if report["infrastructure_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
