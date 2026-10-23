"""Bounded process and JSON pipe transport for development and verification."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time

import numpy as np
from isolation import cleanup

MAX_FRAME = 8 * 1024**2


class TransformError(ValueError):
    pass


class TransformProcess:
    def __init__(self, submission, work, log, deadline, sandbox=False, require_gpu=True):
        self.sandbox = sandbox
        self.buffer = b""
        self.process = None
        work = Path(work)
        work.mkdir(parents=True, exist_ok=True)
        work.chmod(0o777)
        environment = {k: os.environ[k] for k in ("PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES", "SEARCH_SWE_VERIFIER_SANDBOX") if k in os.environ}
        environment.update(HOME=str(work), TMPDIR=str(work), XDG_CACHE_HOME=str(work / "cache"),
                           CUDA_CACHE_PATH=str(work / "cuda-cache"), TRITON_CACHE_DIR=str(work / "triton-cache"),
                           OMP_NUM_THREADS="16", OPENBLAS_NUM_THREADS="16", MKL_NUM_THREADS="16",
                           PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        command = [sys.executable, str(Path(__file__).with_name("worker.py")), "--submission", str(submission), "--work", str(work)]
        if sandbox:
            command.append("--isolate")
        if require_gpu:
            command.append("--require-gpu")
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env=environment, start_new_session=True, bufsize=0)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)

        def drain():
            total = 0
            with Path(log).open("wb") as handle:
                while chunk := self.process.stderr.read(65536):
                    if total < 1024**2:
                        handle.write(chunk[:1024**2 - total])
                    total += len(chunk)

        self.drainer = threading.Thread(target=drain, daemon=True)
        self.drainer.start()
        try:
            if self.read(deadline) != {"ready": True}:
                raise ValueError("Transform did not become ready")
        except BaseException:
            self.close()
            raise

    def read(self, deadline):
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError("Transform response timed out")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("Transform exited before responding")
            self.buffer += chunk
            if len(self.buffer) > MAX_FRAME:
                raise ValueError("Transform response exceeded the frame limit")
        line, self.buffer = self.buffer.split(b"\n", 1)
        result = json.loads(line)
        if not isinstance(result, dict):
            raise ValueError("Transform response is not an object")
        return result

    def transform(self, vectors, languages, deadline):
        payload = json.dumps({"vectors": np.asarray(vectors, dtype=np.float32).tolist(), "languages": list(languages)},
                             allow_nan=False, separators=(",", ":")).encode() + b"\n"
        position = 0
        while position < len(payload):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError("Transform input timed out")
            try:
                position += os.write(self.process.stdin.fileno(), payload[position:])
            except BlockingIOError:
                continue
        response = self.read(deadline)
        if "error" in response:
            raise TransformError(str(response["error"]))
        if set(response) != {"vectors"}:
            raise ValueError("Transform reported an error")
        result = np.asarray(response["vectors"], dtype=np.float32)
        if result.shape != np.asarray(vectors).shape or not np.isfinite(result).all():
            raise ValueError("Invalid transformed vectors")
        if time.monotonic() > deadline:
            raise TimeoutError("Transform serialization exceeded the deadline")
        return result

    def close(self):
        if self.process is not None:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.process.pid, sig)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
            if self.sandbox:
                cleanup()
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
            self.drainer.join(timeout=1)
            if not self.drainer.is_alive():
                self.process.stderr.close()
