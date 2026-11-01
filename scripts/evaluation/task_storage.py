"""Host preparation for tasks using job-specific bounded filesystems."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import uuid


DOWNLOAD_ENV = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy", "NO_PROXY",
                "SSL_CERT_FILE", "SSL_CERT_DIR")


@dataclass(frozen=True)
class StoragePlan:
    task: Path
    variable: str
    cpu_variable: str
    cpus: int

    @classmethod
    def discover(cls, task, config):
        if not (task / "tools/prepare_storage.py").is_file():
            return None
        compose = (task / "environment/docker-compose.yaml").read_text()
        variables = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*_STORAGE_ROOT)(?=[:}])", compose))
        cpu_variables = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*_CPUSET)(?=[:}])", compose))
        if len(variables) != 1 or len(cpu_variables) != 1:
            raise ValueError("Bounded storage requires one STORAGE_ROOT and one CPUSET variable")
        return cls(task, variables.pop(), cpu_variables.pop(), config["environment"]["cpus"])

    def configure_cpus(self, env):
        available = os.sched_getaffinity(0)
        value = env.get(self.cpu_variable, "")
        if value:
            selected = set()
            for item in value.split(","):
                if not re.fullmatch(r"\d+(?:-\d+)?", item):
                    raise ValueError(f"{self.cpu_variable} must contain CPU IDs or ranges, such as 0-3,8-11")
                bounds = list(map(int, item.split("-")))
                first, last = bounds[0], bounds[-1]
                if last < first or last > max(available):
                    raise ValueError(f"{self.cpu_variable} contains an unavailable CPU range")
                selected.update(range(first, last + 1))
            if len(selected) != self.cpus or not selected <= available:
                raise ValueError(f"{self.cpu_variable} must select exactly {self.cpus} available logical CPUs")
        else:
            if len(available) < self.cpus:
                raise ValueError(f"Task requires {self.cpus} logical CPUs; only {len(available)} are available")
            selected = set(sorted(available)[:self.cpus])
            env[self.cpu_variable] = ",".join(map(str, sorted(selected)))
        print(f"Task CPUs: {env[self.cpu_variable]} ({self.cpu_variable})", flush=True)


def docker_output(arguments, env=None):
    return subprocess.run(["docker", *arguments], env=env, check=True,
                          capture_output=True, text=True, timeout=30).stdout


def check_host(env):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("Bounded task storage requires a local Linux x86_64 Docker host")
    missing = [name for name in ("docker", "mkfs.ext4", "dpkg-deb")
               if shutil.which(name) is None]
    if missing:
        raise ValueError("Missing host tools: " + ", ".join(missing)
                         + ". On Ubuntu/Debian, install e2fsprogs and dpkg, plus Docker Engine.")
    if not Path("/dev/fuse").exists():
        raise ValueError("Missing /dev/fuse; enable FUSE on the Docker host (for example sudo modprobe fuse)")
    context = json.loads(docker_output(["context", "inspect"], env))[0]
    endpoint = (None if env.get("DOCKER_CONTEXT") else env.get("DOCKER_HOST")) or context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("unix://"):
        raise ValueError("Bounded task storage requires a local Unix-socket Docker daemon")
    info = json.loads(docker_output(["info", "--format", "{{json .}}"], env))
    security = " ".join(info.get("SecurityOptions", []))
    if (info.get("OSType") != "linux" or "rootless" in security or "userns" in security
            or "desktop" in info.get("OperatingSystem", "").lower()
            or info.get("KernelVersion") != platform.release()):
        raise ValueError("Bounded task storage requires native Linux rootful Docker sharing the host kernel")
    return endpoint


def require_unused(runtime, endpoint):
    """Never unmount storage retained by an unfinished or stopped container."""
    prefix = ["--host", endpoint]
    ids = docker_output([*prefix, "ps", "-aq"]).split()
    if not ids:
        return
    mounts = docker_output([*prefix, "inspect", "--format", "{{json .Mounts}}", *ids])
    for line in mounts.splitlines():
        for mount in json.loads(line) or []:
            source = Path(mount.get("Source", "/"))
            if source == runtime or runtime in source.parents:
                raise RuntimeError(f"Storage is still attached to a Docker container: {runtime}")


def worker(task, runtime_root, run_id, endpoint, owner_uid):
    """Keep the one sudo session alive until Harbor has finished; receive no keys."""
    import fcntl

    signal.signal(signal.SIGINT, signal.SIG_IGN)

    runtime = runtime_root / run_id
    prepare = [sys.executable, str(task / "tools/prepare_storage.py"),
               "--runtime-root", str(runtime_root), "--run-id", run_id]
    cleanup = [*prepare, "--unmount"]
    try:
        # The task's tool cache must not be unpacked by two simultaneous runs.
        with (runtime_root / ".prepare.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            subprocess.run(prepare, check=True, stdout=sys.stderr)
        # Keep the run directory private to the caller. Images, evidence,
        # filesystem roots and verifier markers retain their original ownership.
        os.chown(runtime, owner_uid, -1)
        runtime.chmod(0o700)
        print("ready", flush=True)
        if sys.stdin.readline().strip() != "cleanup":
            raise RuntimeError("Launcher disconnected; run storage has been retained")
        require_unused(runtime, endpoint)
        subprocess.run(cleanup, check=True, stdout=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Storage preparation/cleanup failed: {error}", file=sys.stderr)
        if runtime.exists():
            print("After its containers exit, recover with: sudo " + shlex.join(cleanup), file=sys.stderr)
        return 1


@contextmanager
def prepared_storage(plan, env):
    endpoint = check_host(env)
    plan.configure_cpus(env)
    if env.get(plan.variable):
        runtime = Path(env[plan.variable])
        if not runtime.is_absolute():
            raise ValueError(f"{plan.variable} must be an absolute path")
        print(f"Using caller-managed storage: {runtime}", flush=True)
        yield
        return
    prefix = []
    if os.getuid() != 0:
        sudo = shutil.which("sudo")
        if sudo is None:
            raise ValueError("Storage preparation needs host root or sudo; install/configure sudo first")
        print("Authorizing storage preparation and cleanup with sudo; Harbor retains your user identity.", flush=True)
        subprocess.run([sudo, "-v"], check=True)
        prefix = [sudo, "-n", "--preserve-env=" + ",".join(DOWNLOAD_ENV), "--"]
    root = plan.task.parents[1] / "jobs/.task-storage" / plan.task.name
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_id = "run-" + uuid.uuid4().hex
    runtime = root / run_id
    command = [*prefix, sys.executable, str(Path(__file__).resolve()), "--worker",
               "--task", str(plan.task), "--runtime-root", str(root),
               "--run-id", run_id, "--docker-endpoint", endpoint,
               "--owner-uid", str(os.geteuid())]
    # Only the storage helper is privileged. Model credentials never enter its
    # environment, command line or control pipe. sudo can use the terminal.
    helper_env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TERM", *DOWNLOAD_ENV)
                  if key in os.environ}
    helper = subprocess.Popen(command, env=helper_env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True, start_new_session=not bool(prefix))
    ready = False
    try:
        ready = helper.stdout.readline().strip() == "ready"
        if not ready:
            raise RuntimeError("Bounded storage preparation failed; see the host setup error above")
        env[plan.variable] = str(runtime)
        print(f"Bounded task storage: {runtime}", flush=True)
        yield
    finally:
        try:
            helper.communicate("cleanup\n")
        except BrokenPipeError:
            helper.wait()
        if ready and helper.returncode:
            raise RuntimeError("Storage cleanup is incomplete; retained paths and recovery command are shown above")


def run_command(command, env, cwd):
    """Forward cancellation to Harbor and wait for its container teardown."""
    child = subprocess.Popen(command, env=env, cwd=cwd, start_new_session=True)
    def forward(signum, _frame):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        result = child.wait()
        return result if result >= 0 else 128 - result
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--docker-endpoint", required=True)
    parser.add_argument("--owner-uid", type=int, required=True)
    arguments = parser.parse_args()
    sys.exit(worker(arguments.task, arguments.runtime_root, arguments.run_id,
                    arguments.docker_endpoint, arguments.owner_uid))
