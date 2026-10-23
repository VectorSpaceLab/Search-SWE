"""Bounded JSONL I/O; caller owns timings, limits and process-tree cleanup."""
import json
import os
import select
import signal
import subprocess
import time

MAX_RESPONSE = 128 * 1024


class Process:
    def __init__(self, command, cwd, env, stderr, prepare=None):
        self.stream = open(stderr, "wb")
        self.started = time.monotonic()
        try:
            self.child = subprocess.Popen(command, cwd=cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stream,
                start_new_session=True, bufsize=0, preexec_fn=prepare)
        except BaseException:
            self.stream.close()
            raise
        os.set_blocking(self.child.stdin.fileno(), False)
        os.set_blocking(self.child.stdout.fileno(), False)
        self.buffer = bytearray()

    def request(self, row, deadline, monitor=lambda: None):
        if self.buffer:
            raise ValueError("Unsolicited output after response")
        payload = memoryview((json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n").encode())
        while payload:
            monitor()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Request write exceeded phase budget")
            if select.select([], [self.child.stdin], [], min(.05, remaining))[1]:
                try:
                    payload = payload[os.write(self.child.stdin.fileno(), payload):]
                except BlockingIOError:
                    continue
        while b"\n" not in self.buffer:
            monitor()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Response exceeded phase budget")
            if select.select([self.child.stdout], [], [], min(.05, remaining))[0]:
                chunk = os.read(self.child.stdout.fileno(), MAX_RESPONSE + 1)
                if not chunk:
                    raise ValueError("Submission exited without a response")
                self.buffer.extend(chunk)
                if len(self.buffer) > MAX_RESPONSE:
                    raise ValueError("Response exceeds 128 KiB")
        line, _, extra = self.buffer.partition(b"\n")
        self.buffer = bytearray(extra)
        try:
            return json.loads(line)
        except (UnicodeError, ValueError):
            return None  # Malformed but framed search responses receive zero recall.

    def close(self):
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.child.wait(timeout=5)
        self.child.stdin.close()
        self.child.stdout.close()
        self.stream.close()
