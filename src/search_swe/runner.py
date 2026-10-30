"""Restore fixed inputs and schedule the existing single-task launcher."""

from contextlib import nullcontext
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

from . import __version__
from .resources import gpu_inventory


def backend(root, name):
    key = "_search_swe_backend_" + name
    spec = importlib.util.spec_from_file_location(key, root / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def launch_command(root, task, setting, output=None, allocation=None):
    command = [sys.executable, str(root / "scripts/run_task.py"), "--task", task.name,
               "--no-env-file", *setting.flags()]
    if output is not None:
        command += ["--output", str(output)]
    if allocation is not None:
        command += ["--cpu-set", allocation.cpu_set]
        if allocation.gpu:
            command += ["--gpu-device", allocation.gpu]
    return command


def preflight(root, tasks, setting, env):
    for task in tasks:
        result = subprocess.run([*launch_command(root, task, setting), "--check"],
                                env=env, cwd=root, capture_output=True, text=True)
        if result.returncode:
            # The backend reports variable names, never credential values.
            raise ValueError(f"Configuration for {task.name}:\n{result.stderr.strip()}")


def doctor(root, tasks=(), env=None):
    import platform
    from .resources import Pool
    env = dict(os.environ) if env is None else env
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("Evaluation requires a native Linux x86_64 Docker host")
    missing = [name for name in ("docker", "harbor") if shutil.which(name) is None]
    if missing:
        raise ValueError("Missing executables: " + ", ".join(missing) + "; install the package and Docker Engine")
    context = subprocess.run(["docker", "context", "inspect"], env=env,
                             check=True, capture_output=True, text=True, timeout=30)
    endpoint = ((None if env.get("DOCKER_CONTEXT") else env.get("DOCKER_HOST"))
                or json.loads(context.stdout)[0]["Endpoints"]["docker"]["Host"])
    if not endpoint.startswith("unix://"):
        raise ValueError("Evaluation requires a local Unix-socket Docker daemon")
    response = subprocess.run(["docker", "info", "--format", "{{json .}}"], env=env,
                              check=True, capture_output=True, text=True, timeout=30)
    info = json.loads(response.stdout)
    security = " ".join(info.get("SecurityOptions", []))
    if (info.get("OSType") != "linux" or "rootless" in security or "userns" in security
            or "desktop" in info.get("OperatingSystem", "").lower()
            or info.get("KernelVersion") != platform.release()):
        raise ValueError("Evaluation requires native Linux rootful Docker sharing the host kernel")
    subprocess.run(["docker", "compose", "version", "--short"], env=env, check=True,
                   capture_output=True, text=True, timeout=15)
    if any(task.bounded for task in tasks):
        backend(root, "task_storage").check_host(env)
        if os.getuid() and shutil.which("sudo") is None:
            raise ValueError("Selected tasks need root or sudo for bounded storage")
    return {"checkout": str(root), "docker": info.get("ServerVersion"),
            "logical_cpus": len(os.sched_getaffinity(0)),
            "available_memory_gib": round(Pool.host([]).memory_mb / 1024, 1)}


def private_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def terminate(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass


def wait_cancelled(processes):
    for process in processes:
        terminate(process)
    deadline = time.monotonic() + 120
    for process in processes:
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def run_batch(root, tasks, setting, env, pool, concurrency, output=None, offline=False):
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = Path(output).resolve() if output else root / "jobs/evaluations" / batch_id
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    logs = output / "logs"
    logs.mkdir(mode=0o700)
    try:
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    report = {"cli_version": __version__, "setting": setting.public(), "git_revision": revision, "working_tree_dirty": dirty,
              "concurrency": concurrency, "tasks": {}, "status": "preparing"}
    for task in tasks:
        report["tasks"][task.name] = {"status": "pending", "log": str(logs / f"{task.name}.log"),
                                     "output": str(output / task.name)}
    def record():
        private_json(output / "run.json", report)
    record()
    print(f"Evaluation batch: {output}", flush=True)
    active = []
    storage = backend(root, "task_storage") if any(task.bounded for task in tasks) else None
    pending = list(tasks)
    authorized_sudo = False
    refreshed = 0
    gpu_checked = 0
    idle_gpus = None
    waiting = False
    def cancel(*_):
        raise KeyboardInterrupt
    previous_term = signal.signal(signal.SIGTERM, cancel)
    try:
        # Restore sequentially before scheduling to avoid concurrent asset/cache writes.
        for task in tasks:
            path = logs / f"{task.name}.assets.log"
            print(f"Checking/restoring assets: {task.name} ({task.asset_bytes / 2**30:.2f} GiB manifest); {path}", flush=True)
            command = [sys.executable, str(root / "scripts/download_assets.py"), "--task", task.name, "--force"]
            if offline:
                command.append("--local-files-only")
            with path.open("w") as stream:
                os.fchmod(stream.fileno(), 0o600)
                process = subprocess.Popen(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
                try:
                    code = process.wait()
                except BaseException:
                    wait_cancelled([process])
                    raise
            if code:
                report["tasks"][task.name]["status"] = "asset-error"
                raise RuntimeError(f"Asset restoration failed for {task.name}; see {path}")
        report["status"] = "running"
        while pending or active:
            if any(task.gpus for task in pending) and time.monotonic() - gpu_checked >= 2:
                idle_gpus = {gpu["uuid"] for gpu in gpu_inventory() if gpu["idle"]}
                gpu_checked = time.monotonic()
            if authorized_sudo and time.monotonic() - refreshed > 60:
                subprocess.run(["sudo", "-n", "-v"], check=True)
                refreshed = time.monotonic()
            for task in list(pending):
                if len(active) >= concurrency:
                    break
                allocation = pool.acquire(task, env, idle_gpus)
                if allocation is None:
                    continue
                child_env = dict(env)
                if task.cpu_variable:
                    child_env[task.cpu_variable] = allocation.cpu_set
                context = nullcontext()
                stream = None
                entered = False
                try:
                    if task.bounded:
                        plan = storage.StoragePlan.discover(task.path, task.config)
                        context = storage.prepared_storage(plan, child_env)
                    context.__enter__()
                    entered = True
                    if task.bounded and os.getuid() != 0:
                        authorized_sudo = True
                        refreshed = time.monotonic()
                    row = report["tasks"][task.name]
                    if task.bounded:
                        row["storage_root"] = child_env[plan.variable]
                    stream = Path(row["log"]).open("w")
                    os.fchmod(stream.fileno(), 0o600)
                    command = launch_command(root, task, setting, row["output"], allocation)
                    process = subprocess.Popen(command, cwd=root, env=child_env, stdout=stream,
                                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                               start_new_session=True, umask=0o077)
                except BaseException:
                    if stream:
                        stream.close()
                    try:
                        if entered:
                            context.__exit__(*sys.exc_info())
                    finally:
                        pool.release(allocation)
                    raise
                row.update(status="running", cpu_set=allocation.cpu_set, gpu=allocation.gpu,
                           started=datetime.now(timezone.utc).isoformat())
                active.append((task, allocation, process, stream, context))
                waiting = False
                pending.remove(task)
                print(f"Started {task.name}; CPUs {allocation.cpu_set}; GPU {allocation.gpu or 'none'}; log: {row['log']}", flush=True)
                record()
            for item in list(active):
                task, allocation, process, stream, context = item
                if process.poll() is None:
                    continue
                active.remove(item)
                stream.close()
                row = report["tasks"][task.name]
                row.update(returncode=process.returncode, status="completed" if process.returncode == 0 else "failed")
                try:
                    context.__exit__(None, None, None)
                except Exception as error:
                    row.update(status="cleanup-error", error=str(error))
                pool.release(allocation)
                print(f"{task.name}: {row['status']}; output: {row['output']}", flush=True)
                record()
            if (pending and not active and all(task.gpus for task in pending)
                    and not set(pool.gpus).intersection(idle_gpus or ()) and not waiting):
                print("Waiting for an idle GPU in the selected resource pool; Ctrl-C cancels the batch.", flush=True)
                waiting = True
            if active or pending:
                time.sleep(0.25)
        report["status"] = "completed" if all(row["status"] == "completed" for row in report["tasks"].values()) else "failed"
    except BaseException as error:
        report["status"] = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        if not isinstance(error, KeyboardInterrupt):
            report["error"] = str(error)
        wait_cancelled([item[2] for item in active])
        for task, allocation, process, stream, context in active:
            stream.close()
            row = report["tasks"][task.name]
            row.update(status="cancelled", returncode=process.returncode)
            try:
                context.__exit__(None, None, None)
            except Exception as cleanup_error:
                row.update(status="cleanup-error", error=str(cleanup_error))
            pool.release(allocation)
        for task in pending:
            if report["tasks"][task.name]["status"] == "pending":
                report["tasks"][task.name]["status"] = "not-started"
        raise
    finally:
        record()
        signal.signal(signal.SIGTERM, previous_term)
        print(f"Batch summary: {output / 'run.json'}", flush=True)
    return 0 if report["status"] == "completed" else 1
