"""Verifier-owned sampling of the one leased GPU, including child processes.

NVML API: https://docs.nvidia.com/deploy/nvml-api/latest/api/structnvmlMemory__t.html
The metric is a sampled device-memory peak, not a CUDA allocator self-report.
"""

import ctypes
import subprocess
import threading
import time


class MemoryInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("total", "free", "used")]


class GPUMemoryPeak:
    def __init__(self, uuid, interval=.01):
        if not uuid or not uuid.startswith("GPU-"):
            raise ValueError("Expected the leased physical GPU UUID")
        self.library = ctypes.CDLL("libnvidia-ml.so.1")
        self.check(self.library.nvmlInit_v2())
        self.device = ctypes.c_void_p()
        self.check(self.library.nvmlDeviceGetHandleByUUID(uuid.encode(), ctypes.byref(self.device)))
        self.interval = interval
        self.stop_event = threading.Event()
        self.error = None
        self.samples = 0
        def active_memory():
            # NVML v1 includes driver-reserved bytes (about520MiB here), even
            # on an idle card. nvidia-smi reports active framebuffer use.
            value = subprocess.check_output(
                ["nvidia-smi", f"--id={uuid}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True, timeout=5)
            return int(value.strip())*1024**2

        active = active_memory()
        deadline = time.monotonic()+10
        while active > 64*1024**2 and time.monotonic() < deadline:
            time.sleep(.05)
            active = active_memory()
        if active > 64*1024**2:
            raise ValueError(f"Leased GPU is not idle before a measured phase: active{active}bytes")
        self.idle = self.used()
        self.peak = self.idle
        self.thread = threading.Thread(target=self.sample, daemon=True)

    @staticmethod
    def check(status):
        if status != 0:
            raise RuntimeError(f"NVML returned status{status}")

    def used(self):
        info = MemoryInfo()
        self.check(self.library.nvmlDeviceGetMemoryInfo(self.device, ctypes.byref(info)))
        return int(info.used)

    def sample(self):
        try:
            while not self.stop_event.is_set():
                self.peak = max(self.peak, self.used())
                self.samples += 1
                self.stop_event.wait(self.interval)
        except Exception as error:
            self.error = error

    def start(self):
        self.thread.start()

    def finish(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        try:
            self.peak = max(self.peak, self.used())
        finally:
            self.check(self.library.nvmlShutdown())
        if self.thread.is_alive() or self.error is not None or self.samples < 1:
            raise RuntimeError(f"GPU memory sampling failed: {self.error}")
        return {"metric": "NVML device used memory above phase idle, sampled every10ms",
                "idle_used_bytes": self.idle, "peak_device_used_bytes": self.peak,
                "peak_above_idle_bytes": max(0, self.peak-self.idle),
                "samples": self.samples, "sampling_interval_sec": self.interval,
                "scope": "entire preparation and all queries, all processes on the leased GPU"}
