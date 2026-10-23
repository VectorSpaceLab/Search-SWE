"""Trusted supervisor. Submission code and hidden labels never share a process."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import tempfile
import time

import numpy as np
import pynvml

from isolation import UID, cleanup
from metrics import JS, PROPERTIES, recalls, reward, summarize, validate_ids
from metrics import TARGETS
from gold import feasible as true_feasible, top_ids

PREPARE_SECONDS = 3600.0
QUERY_SECONDS = 2.0
STORAGE_BYTES = 64 << 30


class ResourceViolation(RuntimeError):
    pass


def files_size(root):
    return sum(p.stat().st_size for p in Path(root).rglob("*")
               if not p.is_symlink() and p.is_file())


def writable_bytes():
    # /app uses disk, not a RAM-backed tmpfs. Account for logical bytes, including
    # sparse and open-unlinked files, without counting unrelated image layers.
    seen = set()
    total = 0
    def account(path, descriptor=False):
        nonlocal total
        if descriptor:
            destination = os.readlink(path)
            if not destination.startswith(("/app/", "/dev/shm/", "/memfd:")):
                return
        elif path.is_symlink():
            return
        info = path.stat()
        identity = info.st_dev, info.st_ino
        if stat.S_ISREG(info.st_mode) and identity not in seen:
            total += info.st_size
            seen.add(identity)

    for path in [*Path("/app").rglob("*"), *Path("/dev/shm").rglob("*")]:
        try:
            account(path)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise ResourceViolation("Cannot account for task storage") from error
    libc = ctypes.CDLL(None)
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            status = (process / "status").read_text().splitlines()
            real_uid = int(next(line.split()[1] for line in status if line.startswith("Uid:")))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if real_uid != UID and int(process.name) != os.getpid():
            continue
        # procfs checks filesystem UID AND GID. Keep real/effective/saved root
        # credentials, so the submission cannot inspect the supervisor. Changing
        # only fsids avoids CAP_SYS_PTRACE, forbidden by the egress gateway.
        attempt = 0
        exit_deadline = None
        while True:
            previous_gid = libc.setfsgid(UID) if real_uid == UID else None
            previous_uid = libc.setfsuid(UID) if real_uid == UID else None
            denied = False
            try:
                for path in (process / "fd").iterdir():
                    try:
                        account(path, descriptor=True)
                    except (FileNotFoundError, ProcessLookupError):
                        continue
            except (FileNotFoundError, ProcessLookupError):
                break
            except PermissionError:
                denied = True
            finally:
                if previous_uid is not None:
                    libc.setfsuid(previous_uid)
                    libc.setfsgid(previous_gid)
            if not denied:
                break
            try:
                state = (process / "status").read_text()
                # PF_EXITING precedes the zombie state. In particular, after
                # exit_mm() procfs may deny fd inspection while exit_files()
                # has not finished. Wait for actual exit instead of treating a
                # normal process-pool shutdown as deliberate non-dumpability.
                fields = (process / "stat").read_text().rsplit(") ", 1)[1].split()
                exiting = bool(int(fields[6]) & 0x00000004)
            except (FileNotFoundError, ProcessLookupError):
                break
            if any(line.startswith("State:") and "Z" in line for line in state.splitlines()):
                break  # Zombies hold no descriptors.
            if exiting:
                if exit_deadline is None:
                    exit_deadline = time.monotonic() + 1.0
                if time.monotonic() < exit_deadline:
                    time.sleep(.005)
                    continue
            if attempt == 0:
                attempt += 1
                time.sleep(.005)  # Allow the worker's brief setuid/dumpable transition.
            else:
                raise ResourceViolation("Submission processes must remain inspectable for storage accounting")
    return total


def snapshot():
    root = Path("/app/submission")
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Missing regular /app/submission directory")
    hashes = {}
    for path in [root, *root.rglob("*")]:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Submission must contain regular files and directories only")
        executable = bool(path.stat().st_mode & 0o111)
        os.chown(path, 0, 0)
        path.chmod(0o555 if path.is_dir() or executable else 0o444)
        if path.is_file():
            with path.open("rb") as source:
                hashes[str(path.relative_to(root))] = hashlib.file_digest(source, "sha256").hexdigest()
    if "retriever.py" not in hashes:
        raise ValueError("Missing retriever.py")
    return hashes


class Resources:
    def __init__(self, fixed_bytes):
        self.fixed_bytes = fixed_bytes
        self.peak_storage = self.peak_gpu = 0
        self.last_disk = 0.0
        pynvml.nvmlInit()
        if pynvml.nvmlDeviceGetCount() != 1:
            raise ResourceViolation("Exactly one mapped GPU is required")
        self.gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(self.gpu)
        capacity = pynvml.nvmlDeviceGetMemoryInfo(self.gpu).total
        if "A100" not in name or not (39 << 30) <= capacity <= (41 << 30):
            raise ResourceViolation("The task requires an A100 40GB")
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        maximum = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if quota == "max" or int(quota) / int(period) > 16:
            raise ResourceViolation("CPU cgroup limit must be at most 16 cores")
        if maximum == "max" or int(maximum) > 32 << 30:
            raise ResourceViolation("Memory cgroup limit must be at most 32 GiB")

    def check(self, force=False):
        self.peak_gpu = max(self.peak_gpu, pynvml.nvmlDeviceGetMemoryInfo(self.gpu).used)
        if force or time.monotonic() - self.last_disk >= .5:
            self.last_disk = time.monotonic()
            used = self.fixed_bytes + writable_bytes()
            self.peak_storage = max(self.peak_storage, used)
            if used > STORAGE_BYTES:
                raise ResourceViolation("64 GiB total task storage exceeded")

    def report(self):
        path = Path("/sys/fs/cgroup/memory.peak")
        return {"gpu": pynvml.nvmlDeviceGetName(self.gpu),
                "gpu_uuid": pynvml.nvmlDeviceGetUUID(self.gpu),
                "peak_gpu_bytes": self.peak_gpu, "peak_task_storage_bytes": self.peak_storage,
                "container_memory_peak_bytes": int(path.read_text()) if path.exists() else None}


class Worker:
    def __init__(self, work, output, resources, library_dir):
        self.work, self.resources = work, resources
        fd, _ = tempfile.mkstemp(prefix="worker-stderr-", dir=work)
        self.log = os.fdopen(fd, "a+b")
        self.report_log = output / "worker.stderr.log"
        env = {name: os.environ[name] for name in (
            "PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES",
            "NVIDIA_DRIVER_CAPABILITIES") if name in os.environ}
        env.update(HOME=str(work), TMPDIR=str(work), XDG_CACHE_HOME=str(work / "cache"),
                   MOLECULE_WORK_DIR=str(work), MOLECULE_LIBRARY_DIR=str(library_dir),
                   PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="16",
                   OPENBLAS_NUM_THREADS="16", MKL_NUM_THREADS="16")
        self.process = subprocess.Popen(["/opt/conda/bin/python", "/task/runtime/worker.py"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, env=env, bufsize=0)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b""

    def call(self, message, deadline):
        payload = memoryview((json.dumps(message, separators=(",", ":")) + "\n").encode())
        while payload:
            if time.monotonic() >= deadline:
                raise TimeoutError("Input delivery deadline exceeded")
            try:
                written = os.write(self.process.stdin.fileno(), payload)
                payload = payload[written:]
            except BlockingIOError:
                self.resources.check()
                time.sleep(.001)
        while b"\n" not in self.buffer:
            self.resources.check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Response deadline exceeded")
            if self.selector.select(min(.02, remaining)):
                block = os.read(self.process.stdout.fileno(), 65536)
                if not block:
                    raise RuntimeError("Submission worker exited")
                self.buffer += block
                if len(self.buffer) > 2 << 20:
                    raise ValueError("Response exceeds 2 MiB")
        line, self.buffer = self.buffer.split(b"\n", 1)
        if self.buffer:
            raise ValueError("Unsolicited submission output")
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError("Response must be a JSON object")
        return response

    def close(self):
        cleanup()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.flush()
        size = self.log.seek(0, 2)
        self.log.seek(max(0, size - (8 << 20)))
        with self.report_log.open("ab") as destination:
            destination.write(f"\n[worker stderr: {size} bytes; retained last 8 MiB]\n".encode())
            shutil.copyfileobj(self.log, destination)
        self.log.close()


def evaluate(private_dir, output, library_dir="/task/library", reference_dir=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    private = Path(private_dir)
    reference = Path(reference_dir) if reference_dir else private
    manifest = json.loads((Path(library_dir) / "library.json").read_text())
    queries = [json.loads(line) for line in (reference / "queries.jsonl").read_text().splitlines() if line]
    if not queries or len({q["query_id"] for q in queries}) != len(queries):
        raise ValueError("Missing or duplicate evaluation queries")
    truth_path = reference / "truth.npz"
    truth = np.load(truth_path, allow_pickle=False) if truth_path.exists() else None
    scores = np.load(private / "scores.npy", mmap_mode="r", allow_pickle=False) if truth is None else None
    properties = np.load(private / "properties.npy", mmap_mode="r", allow_pickle=False)
    hashes = snapshot()
    resources = Resources(manifest["fixed_public_bytes"])
    work = Path(tempfile.mkdtemp(prefix="molecules-", dir="/app"))
    work.chmod(0o700)
    os.chown(work, UID, UID)
    rows, preparation = [], 0.0
    worker = None
    first = True
    started = time.monotonic()
    try:
        for query in queries:
            expected = (truth[query["query_id"]] if truth is not None else
                        top_ids(scores[:, TARGETS.index(query["target"])],
                                true_feasible(properties, query["constraints"]), query["k"]))
            if worker is None:
                tick = time.monotonic()
                worker = Worker(work, output, resources, library_dir)
                ready = worker.call({"op": "prepare" if first else "load"},
                                    tick + PREPARE_SECONDS - preparation)
                preparation += time.monotonic() - tick
                if ready != {"ready": True} or preparation > PREPARE_SECONDS:
                    raise RuntimeError("Final preparation failed or exceeded 3600 seconds")
                first = False
            row = {"query_id": query["query_id"], "target": query["target"],
                   "main": query.get("main", True), "recalls": [0.0] * len(JS),
                   "status": "invalid", "output_count": 0,
                   "constraints": query["constraints"], "configuration_id": query.get("configuration_id"),
                   "true_feasible_count": query.get("true_feasible_count")}
            tick = time.monotonic()
            try:
                # No evaluator-only counts, grouping or diagnostic metadata
                # cross the worker boundary.
                request = {key: query[key] for key in ("query_id", "target", "constraints", "k")}
                response = worker.call(request, tick + QUERY_SECONDS)
                if response.get("query_id") != query["query_id"] or "error" in response:
                    raise ValueError("Query ID mismatch or submission error")
                ids = validate_ids(response.get("ids"), manifest["n_products"], query["k"])
                row["seconds"] = time.monotonic() - tick
                if row["seconds"] > QUERY_SECONDS:
                    raise TimeoutError("Complete ID response exceeded 2 seconds")
                row.update(status="ok", output_count=len(ids))
                if row["main"]:
                    row["recalls"] = recalls(ids, expected, (query["k"],))
                feasible = np.ones(len(ids), dtype=bool)
                for name, (lower, upper) in query["constraints"].items():
                    values = properties[ids, PROPERTIES.index(name)]
                    if lower is not None:
                        feasible &= values >= lower
                    if upper is not None:
                        feasible &= values <= upper
                row["true_constraint_satisfaction"] = float(np.mean(feasible)) if len(ids) else 0.0
                row["feasible_output_count"] = int(feasible.sum())
            except ResourceViolation:
                raise
            except (TimeoutError, ValueError, RuntimeError, BrokenPipeError, OSError) as error:
                row.update(seconds=time.monotonic() - tick, failure=str(error),
                           status="timeout" if isinstance(error, TimeoutError) else "invalid")
                worker.close()
                worker = None
            rows.append(row)
            (output / "query-metrics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        resources.check(force=True)
        q, targets = summarize(rows)
        latencies = [r["seconds"] for r in rows]
        return {"valid": True, "reward": reward(q, 0.0, 1.0),
                "Q": q, "B": 0.0, "U": 1.0, "by_target": targets,
                "preparation_seconds": preparation, "total_seconds": time.monotonic() - started,
                "latency_p50": float(np.median(latencies)), "latency_p95": float(np.percentile(latencies, 95)),
                "latency_max": max(latencies), "queries": rows, "resources": resources.report(),
                "submission_bytes": files_size("/app/submission"),
                "index_bytes": files_size(work / "index"), "scratch_bytes": files_size(work),
                "submission_sha256": hashes}
    finally:
        if worker is not None:
            worker.close()
        cleanup()
        shutil.rmtree(work)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--library-dir", default="/task/library")
    parser.add_argument("--reference-dir")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"valid": False, "reward": 0.0}
    try:
        report = evaluate(args.private_dir, output, args.library_dir,
                          args.reference_dir)
    except Exception as error:
        report["failure"] = type(error).__name__ + ": " + str(error)
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
