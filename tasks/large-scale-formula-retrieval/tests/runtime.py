"""Privileged supervisor for a credential-free, stopped-between-phases worker."""
import ctypes
import errno
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import time

import psutil

UID = 10001
MEMORY = 4 << 30
STORAGE = 64 << 30
MAX_LINE = 1 << 20
MAX_DIAGNOSTICS = 128 << 20
_diagnostic_bytes = 0  # Shared across restarts, within the 512 MiB log reserve.


class ArgComparison(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int),
                ('datum_a', ctypes.c_uint64), ('datum_b', ctypes.c_uint64)]


class Violation(RuntimeError):
    pass


def clear_worker_ipc():
    """Remove submitted kernel IPC state from the verifier's private namespace."""
    objects = []
    for table, identifier, command in [('shm', 'shmid', 'shmctl'),
                                       ('msg', 'msqid', 'msgctl'),
                                       ('sem', 'semid', 'semctl')]:
        path = Path('/proc/sysvipc', table)
        if not path.exists():
            continue
        rows = path.read_text().splitlines()
        for line in rows[1:]:
            row = dict(zip(rows[0].split(), line.split()))
            if int(row['uid']) == UID:
                objects.append((int(row[identifier]), command))
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        os.seteuid(UID)
        for identifier, command in objects:
            result = (libc.semctl(identifier, 0, 0) if command == 'semctl'
                      else getattr(libc, command)(identifier, 0, None))
            if result != 0 and ctypes.get_errno() not in [errno.EINVAL, errno.EIDRM]:
                raise Violation('cannot clear submitted kernel IPC state')
    finally:
        os.seteuid(0)


def sandbox(cpu_ids, work):
    os.sched_setaffinity(0, cpu_ids)
    # Prefer terminating the over-budget candidate over the small trusted grader.
    Path('/proc/self/oom_score_adj').write_text('1000')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (STORAGE, STORAGE))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), 'prctl')
    sec = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(ArgComparison)]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7fff0000)  # allow
    if not ctx:
        raise RuntimeError('seccomp initialization failed')
    try:
        # Docker's cpuset is the hard CPU boundary in every phase. Legitimate
        # thread pinning within those assigned cores does not need to be blocked.
        for call in ['ptrace', 'process_vm_readv',
                     'process_vm_writev', 'setns', 'unshare', 'mount', 'umount2',
                     'bpf', 'perf_event_open', 'io_uring_setup']:
            nr = sec.seccomp_syscall_resolve_name(call.encode())
            if nr >= 0 and sec.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, nr, 0):
                raise RuntimeError('seccomp rule failed')
        # Local Unix IPC is legitimate (e.g. multiprocessing.Pipe); Internet and
        # other address families are unavailable. SCMP_CMP_NE=1, AF_UNIX=1.
        condition = ArgComparison(0, 1, 1, 0)
        for call in ['socket', 'socketpair']:
            nr = sec.seccomp_syscall_resolve_name(call.encode())
            if sec.seccomp_rule_add_array(ctx, 0x50000 | errno.EPERM, nr, 1, ctypes.byref(condition)):
                raise RuntimeError('network seccomp rule failed')
        if sec.seccomp_load(ctx):
            raise RuntimeError('seccomp load failed')
    finally:
        sec.seccomp_release(ctx)
    os.setgroups([])
    os.setgid(UID)
    os.setuid(UID)
    os.chdir(work)


class Worker:
    def __init__(self, command, work, log, cpu_ids, fixed_bytes=0):
        self.work, self.cpus, self.fixed_bytes = Path(work), cpu_ids, fixed_bytes
        self.disk_root = self.work
        self.work.mkdir(parents=True, exist_ok=True)
        os.chown(self.work, UID, UID)
        self.stderr = Path(log).open('wb', buffering=0)
        self.stderr_bytes = 0
        env = {'PATH': '/opt/conda/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(work),
               'TMPDIR': str(work), 'XDG_CACHE_HOME': str(work), 'LANG': 'C.UTF-8',
               'OMP_NUM_THREADS': str(len(cpu_ids)), 'OPENBLAS_NUM_THREADS': str(len(cpu_ids)), 'MKL_NUM_THREADS': str(len(cpu_ids)),
               'OMP_PROC_BIND': 'false', 'KMP_AFFINITY': 'disabled',
               'NUMEXPR_NUM_THREADS': str(len(cpu_ids)), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
        self.launch_start = time.monotonic()
        self.first_phase = True
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env, start_new_session=True,
                                        preexec_fn=lambda: sandbox(cpu_ids, work))
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, 'stdout')
        self.selector.register(self.process.stderr, selectors.EVENT_READ, 'stderr')
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.buffer = bytearray()
        self.last_sample = self.last_disk = 0
        self.peak = self.disk_peak = self.lifetime_peak = 0
        self.phase_start = time.monotonic()

    def members(self):
        # Includes double-forked/reparented processes: isolated verifier owns this UID.
        return [p for p in psutil.process_iter(['uids']) if p.info['uids'] and p.info['uids'].real == UID]

    def sample(self, force=False):
        now = time.monotonic()
        if force or now - self.last_sample >= .01:
            rss = 0
            for p in self.members():
                try:
                    rss += p.memory_info().rss
                except psutil.NoSuchProcess:
                    continue
            self.peak = max(self.peak, rss)
            self.lifetime_peak = max(self.lifetime_peak, rss)
            self.last_sample = now
            # Aggregate RSS double-counts shared pages in multiprocess indexes.
            # Keep it as a diagnostic, but enforce the container's actual charge,
            # including page cache and descendants, consistent with Docker.
            if int(Path('/sys/fs/cgroup/memory.current').read_text()) > MEMORY:
                raise Violation('memory limit')
        if force or now - self.last_disk >= .5:
            size = self.fixed_bytes + os.fstat(self.stderr.fileno()).st_size
            seen = set()
            for base, dirs, files in os.walk(self.disk_root, followlinks=False):
                for name in files:
                    p = Path(base) / name
                    if p in [self.disk_root / '.submission-reserve', self.disk_root / '.storage.json']:
                        continue
                    try:
                        if not p.is_symlink():
                            st = p.stat()
                            identity = (st.st_dev, st.st_ino)
                            if identity not in seen:
                                seen.add(identity)
                                size += max(st.st_size, st.st_blocks * 512)
                    except FileNotFoundError:
                        pass
            self.disk_peak = max(self.disk_peak, size)
            self.last_disk = now
            if size > STORAGE:
                raise Violation('storage limit')

    def begin(self, timeout, query=False):
        members = self.members()
        # Same effective UID can set the stopped worker's affinity without
        # SYS_NICE. Keep real/saved UID 0 and restore it before any grading I/O.
        try:
            os.seteuid(UID)
            for p in members:
                try:
                    threads = p.threads()
                except psutil.NoSuchProcess:
                    continue
                for t in threads:
                    try:
                        os.sched_setaffinity(t.id, self.cpus)
                    except ProcessLookupError:
                        pass  # A thread that finished cannot consume a query CPU.
        finally:
            os.seteuid(0)
        self.sample(True)
        self.phase_start = self.launch_start if self.first_phase else time.monotonic()
        self.first_phase = False
        self.deadline = self.phase_start + timeout
        self.peak = 0
        for p in members:
            p.send_signal(signal.SIGCONT)

    def check(self):
        if time.monotonic() > self.deadline:
            raise Violation('phase timeout')
        if self.process.poll() is not None:
            raise Violation(f'worker exited {self.process.returncode}')
        self.pump(0)
        self.sample()

    def pump(self, wait):
        global _diagnostic_bytes
        for key, _ in self.selector.select(wait):
            chunk = os.read(key.fd, 65536)
            if key.data == 'stderr':
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    continue
                kept = chunk[:max(0, MAX_DIAGNOSTICS - _diagnostic_bytes)]
                self.stderr.write(kept)
                self.stderr_bytes += len(kept)
                _diagnostic_bytes += len(kept)
            else:
                if not chunk:
                    raise Violation('worker closed stdout')
                self.buffer.extend(chunk)
                if len(self.buffer) > MAX_LINE:
                    raise Violation('protocol output exceeds 1 MiB')

    def request(self, obj):
        if self.buffer:
            raise Violation('unsolicited protocol output')
        data = memoryview((json.dumps(obj, separators=(',', ':'), allow_nan=False) + '\n').encode())
        while data:
            self.check()
            try:
                data = data[os.write(self.process.stdin.fileno(), data):]
            except BlockingIOError:
                time.sleep(.001)
        while b'\n' not in self.buffer:
            self.check()
            if b'\n' not in self.buffer:
                self.pump(min(.01, max(0, self.deadline - time.monotonic())))
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        self.last_response_text = line.decode('utf-8', errors='replace')
        try:
            return json.loads(line)
        except (ValueError, UnicodeError, RecursionError):
            return None  # A malformed query response earns zero, preserving the denominator.

    def finish(self):
        # Stop all worker processes before any untimed scoring or next-phase preparation.
        for _ in range(10):
            members = self.members()
            for p in members:
                try:
                    p.send_signal(signal.SIGSTOP)
                except psutil.NoSuchProcess:
                    pass
            stopped = True
            for p in self.members():
                try:
                    stopped &= p.status() in [psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE]
                except psutil.NoSuchProcess:
                    pass
            if stopped:
                break
            time.sleep(.001)
        else:
            raise Violation('cannot suspend complete process family')
        elapsed = time.monotonic() - self.phase_start
        self.sample(True)
        if elapsed > self.deadline - self.phase_start:
            raise Violation('phase timeout')
        if self.peak <= 0:
            raise Violation('missing memory measurement')
        return {'seconds': elapsed, 'rss_bytes': self.peak, 'storage_bytes': self.disk_peak}

    def close(self):
        for p in self.members():
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        self.process.wait(timeout=10)
        clear_worker_ipc()
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.stderr.close()
        self.stderr.close()
