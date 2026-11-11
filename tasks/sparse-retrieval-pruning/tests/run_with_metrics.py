#!/usr/bin/env python3
"""External exit-event timing and bounded, isolated single-CPU invocation."""
import json
import ctypes
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import traceback

import psutil
from isolate import launch, UID


def stop_members():
    for p in psutil.process_iter(['uids']):
        try:
            if p.info['uids'].real == UID:
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def run(command, *, metrics_path, log_prefix, timeout, readable, writable, scratch, cpu):
    env = {'JAVA_HOME': '/opt/java/openjdk',
           'PATH': '/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin',
           'HOME': str(scratch), 'TMPDIR': str(scratch), 'LANG': 'C.UTF-8',
           'USER': 'submission', 'LOGNAME': 'submission', 'PYTHONUNBUFFERED': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS'):
        env[key] = '1'
    def prepare():
        os.environ.clear()
        os.environ.update(env)
        try:
            launch(command, readable, writable, readable[0], cpu)
        except BaseException:
            traceback.print_exc()
            raise
    error = None
    max_python_processes = max_threads = 0
    with open(str(log_prefix) + '.stdout.log', 'wb') as out, open(str(log_prefix) + '.stderr.log', 'wb') as err:
        start = time.monotonic()
        p = subprocess.Popen(command, preexec_fn=prepare, stdout=out, stderr=err, start_new_session=True)
        # The pinned Conda Python was built without os.pidfd_open, although
        # the supported x86_64 Linux kernel provides the pidfd_open syscall.
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.syscall(ctypes.c_long(434), ctypes.c_int(p.pid), ctypes.c_uint(0))
        if fd < 0:
            p.kill()
            p.wait()
            raise OSError(ctypes.get_errno(), "pidfd_open failed")
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(fd, selectors.EVENT_READ)
                while True:
                    remaining = timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        error = 'timeout'
                        break
                    if selector.select(min(0.01, remaining)):
                        break
                    processes = []
                    for member in psutil.process_iter(['uids', 'name', 'num_threads', 'status']):
                        try:
                            if member.info['uids'].real == UID and member.info['status'] != psutil.STATUS_ZOMBIE:
                                processes.append(member.info)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    threads = max((x['num_threads'] for x in processes), default=0)
                    python_count = sum(x['name'].startswith('python') for x in processes)
                    max_python_processes = max(max_python_processes, python_count)
                    max_threads = max(max_threads, threads)
                    if threads > 1 or python_count > 1:
                        error = 'single-process/single-thread restriction violated'
                        break
            elapsed = time.monotonic() - start
            if error:
                try: os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            pid, status, usage = os.wait4(p.pid, 0)
            p.returncode = os.waitstatus_to_exitcode(status)
        finally:
            os.close(fd)
            stop_members()
    metrics = {'command': command, 'return_code': p.returncode, 'error': error,
               'wall_seconds': elapsed, 'timeout_seconds': timeout, 'cpu_affinity': [cpu],
               'user_cpu_seconds': usage.ru_utime, 'system_cpu_seconds': usage.ru_stime,
               'max_rss_kb': usage.ru_maxrss, 'major_page_faults': usage.ru_majflt,
               'minor_page_faults': usage.ru_minflt, 'max_sampled_threads': max_threads,
               'max_sampled_python_processes': max_python_processes}
    Path(metrics_path).write_text(json.dumps(metrics, indent=2, allow_nan=False) + '\n')
    if error or p.returncode:
        raise RuntimeError(f'{command[0]} failed: {error or p.returncode}')
    return metrics
