"""Resource accounting for evaluations owned by one CLI invocation."""

from dataclasses import dataclass
import os
import re
import subprocess

import psutil


def cpu_ids(value):
    result = set()
    for item in value.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", item):
            raise ValueError("CPU pool must contain IDs/ranges such as 0-15,32-47")
        bounds = list(map(int, item.split("-")))
        first, last = bounds[0], bounds[-1]
        if last < first or last > 1_000_000:
            raise ValueError("Invalid CPU range")
        result.update(range(first, last + 1))
    return result


def gpu_inventory():
    try:
        response = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("GPU tasks require nvidia-smi and a working NVIDIA driver") from error
    devices = []
    for line in response.stdout.splitlines():
        index, identity, used, utilization = [part.strip() for part in line.split(",")]
        if not identity.startswith("GPU-"):
            raise ValueError("Unsupported GPU inventory; select full physical GPUs")
        devices.append({"index": index, "uuid": identity, "idle": float(used) <= 512 and float(utilization) <= 5})
    return devices


@dataclass(frozen=True)
class Allocation:
    cpus: frozenset
    memory_mb: int
    gpu: str | None

    @property
    def cpu_set(self):
        return ",".join(map(str, sorted(self.cpus)))


class Pool:
    def __init__(self, cpus, memory_mb, gpus):
        self.cpus = set(cpus)
        self.memory_mb = memory_mb
        self.gpus = list(gpus)
        self.used = []

    @classmethod
    def host(cls, tasks, cpu_set=None, gpu_devices=None, memory_gb=None):
        if not hasattr(os, "sched_getaffinity"):
            raise ValueError("Evaluation requires a Linux Docker host")
        available = os.sched_getaffinity(0)
        cpus = cpu_ids(cpu_set) if cpu_set else available
        if not cpus <= available:
            raise ValueError("CPU pool includes unavailable logical CPUs")
        memory = max(0, psutil.virtual_memory().available // 2**20 - 2048)
        if memory_gb is not None:
            if memory_gb <= 0:
                raise ValueError("--memory-gb must be positive")
            memory = min(memory, int(memory_gb * 1024))
        gpus = []
        if any(task.gpus for task in tasks):
            inventory = gpu_inventory()
            if gpu_devices:
                requested = gpu_devices.split(",")
                for value in requested:
                    matches = [gpu for gpu in inventory if value in (gpu["index"], gpu["uuid"])]
                    if not matches or not matches[0]["idle"]:
                        raise ValueError(f"GPU {value} is unavailable or currently busy")
                    if matches[0]["uuid"] in gpus:
                        raise ValueError("GPU pool contains the same device more than once")
                    gpus.append(matches[0]["uuid"])
            else:
                gpus = [gpu["uuid"] for gpu in inventory if gpu["idle"]]
        return cls(cpus, memory, gpus)

    def fixed_cpus(self, task, env):
        name = task.cpu_variable
        selected = cpu_ids(env[name]) if name and env.get(name) else None
        if selected is not None and (len(selected) != task.cpus or not selected <= self.cpus):
            raise ValueError(f"{name} must select {task.cpus} logical CPUs inside the CPU pool")
        return selected

    def validate(self, tasks, env):
        for task in tasks:
            self.fixed_cpus(task, env)
            if task.cpus > len(self.cpus) or task.memory_mb + 512 > self.memory_mb:
                raise ValueError(f"Insufficient CPU/RAM for {task.name}: needs {task.cpus} CPUs and "
                                 f"{task.memory_mb / 1024:g} GiB RAM plus host/gateway headroom")
            if task.gpus > 1 or (task.gpus and not self.gpus):
                raise ValueError(f"No idle supported GPU available for {task.name}")

    def acquire(self, task, env, idle_gpus=None):
        busy_cpus = set().union(*(allocation.cpus for allocation in self.used))
        available = self.cpus - busy_cpus
        selected = self.fixed_cpus(task, env)
        if selected is None:
            selected = set(sorted(available)[:task.cpus])
        memory = task.memory_mb + 512  # Trusted gateway and orchestration headroom.
        if len(selected) < task.cpus or not selected <= available:
            return None
        if sum(item.memory_mb for item in self.used) + memory > self.memory_mb:
            return None
        free_gpus = [gpu for gpu in self.gpus if gpu not in {item.gpu for item in self.used}
                     and (idle_gpus is None or gpu in idle_gpus)]
        if task.gpus and not free_gpus:
            return None
        allocation = Allocation(frozenset(selected), memory, free_gpus[0] if task.gpus else None)
        self.used.append(allocation)
        return allocation

    def release(self, allocation):
        self.used.remove(allocation)
