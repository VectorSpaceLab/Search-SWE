"""Isolated persistent submission process with bounded JSONL I/O."""
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
MAX_LINE = 1 << 20


class Comparison(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int),
                ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]


class Violation(RuntimeError):
    pass


def isolate(cpus, work):
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 30, 64 << 30))
    Path('/proc/self/oom_score_adj').write_text('1000')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), 'no_new_privs')
    sec = ctypes.CDLL('libseccomp.so.2')
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(Comparison)]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError('seccomp init failed')
    try:
        for call in ('ptrace', 'process_vm_readv', 'process_vm_writev',
                     'sched_setaffinity', 'unshare', 'setns', 'mount', 'umount2', 'bpf',
                     'perf_event_open', 'io_uring_setup'):
            nr = sec.seccomp_syscall_resolve_name(call.encode())
            if nr >= 0 and sec.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, nr, 0):
                raise RuntimeError('seccomp rule failed')
        # Keep local multiprocessing IPC; deny all Internet socket families.
        condition = Comparison(0, 1, 1, 0)  # arg0 != AF_UNIX
        for call in ('socket', 'socketpair'):
            nr = sec.seccomp_syscall_resolve_name(call.encode())
            if sec.seccomp_rule_add_array(ctx, 0x50000 | errno.EPERM, nr, 1, ctypes.byref(condition)):
                raise RuntimeError('socket rule failed')
        if sec.seccomp_load(ctx):
            raise RuntimeError('seccomp load failed')
    finally:
        sec.seccomp_release(ctx)
    os.setgroups([])
    os.setgid(UID)
    os.setuid(UID)
    os.chdir(work)


def members():
    for proc in psutil.process_iter(['uids']):
        if proc.info['uids'] and proc.info['uids'].real == UID:
            yield proc


def signal_members(sig):
    for proc in members():
        try: proc.send_signal(sig)
        except psutil.NoSuchProcess: pass


def writable_size(root, deadline=None):
    seen, size = set(), 0
    for base, dirs, files in os.walk(root, followlinks=False):
        if deadline is not None and time.monotonic() > deadline:
            raise Violation('timeout checking storage')
        for number, name in enumerate(files):
            if number % 64 == 0 and deadline is not None and time.monotonic() > deadline:
                raise Violation('timeout checking storage')
            p = Path(base) / name
            try:
                s = p.lstat()
                if p.is_symlink(): continue
                key = s.st_dev, s.st_ino
                if key not in seen:
                    seen.add(key)
                    size += max(s.st_size, s.st_blocks * 512)
            except FileNotFoundError: pass
    return size


def asset_size(root):
    """Canonical immutable bytes, independent of host filesystem block size."""
    return sum(p.stat().st_size for p in Path(root).rglob('*')
               if p.is_file() and not p.is_symlink())


class Worker:
    def __init__(self, command, work, log, cpus, fixed_bytes=0):
        if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0):  # adopt double-forked descendants
            raise RuntimeError('Cannot enable child subreaper')
        self.work, self.fixed_bytes = work, fixed_bytes
        self.peak_rss = self.peak_storage = 0
        self.last_disk = self.last_sample = 0
        log = Path(log)
        # A sequence of failed queries must not create unbounded trusted logs.
        existing_logs = sum(p.stat().st_size for p in log.parent.glob('worker-*.stderr'))
        self.log_limit = min(8 << 20, max(0, (128 << 20)-existing_logs))
        self.log = log.open('wb', buffering=0)
        self.logged = 0
        env = {'PATH': '/opt/conda/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': work,
               'TMPDIR': work, 'XDG_CACHE_HOME': work, 'PYTHONDONTWRITEBYTECODE': '1',
               'PYTHONUNBUFFERED': '1', 'LANG': 'C.UTF-8', 'OMP_NUM_THREADS': str(len(cpus)),
               'OPENBLAS_NUM_THREADS': str(len(cpus)), 'MKL_NUM_THREADS': str(len(cpus)),
               'OMP_PROC_BIND': 'false', 'KMP_AFFINITY': 'disabled'}
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, env=env, start_new_session=True,
                                            preexec_fn=lambda: isolate(cpus, work))
        except OSError as exc:
            self.log.close()
            if exc.errno in (errno.ENOEXEC, errno.EACCES, errno.ENOENT, errno.ELOOP, errno.ENOTDIR):
                raise Violation(f'Cannot launch submission: {exc.strerror}') from exc
            raise
        self.selector = selectors.DefaultSelector()
        for stream in (self.process.stdout, self.process.stderr):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.buffer = bytearray()

    def sample(self, force_disk=False, deadline=None):
        now = time.monotonic()
        if now - self.last_sample >= .02:
            rss = psutil.Process().memory_info().rss
            for proc in members():
                try: rss += proc.memory_info().rss
                except psutil.NoSuchProcess: pass
            self.peak_rss = max(self.peak_rss, rss)
            self.last_sample = now
            # Docker cgroup limits physical aggregate memory, including page cache.
            # Summed RSS alone would double-charge pages shared after a fork.
        if force_disk or now - self.last_disk >= .5:
            size = self.fixed_bytes + writable_size(self.work, deadline=deadline)
            self.peak_storage = max(self.peak_storage, size)
            self.last_disk = now
            if size > 64 << 30: raise Violation('aggregate storage exceeded')

    def pump(self, deadline):
        if time.monotonic() > deadline: raise Violation('timeout')
        self.sample(deadline=deadline)
        for key, _ in self.selector.select(min(.01, max(0, deadline-time.monotonic()))):
            data = os.read(key.fd, 65536)
            if not data:
                self.selector.unregister(key.fileobj)
                if key.fileobj is self.process.stdout: raise Violation('submission exited')
                continue
            if key.fileobj is self.process.stderr:
                kept = data[:max(0, self.log_limit-self.logged)]
                self.log.write(kept)
                self.logged += len(kept)
            else:
                self.buffer.extend(data)
                if len(self.buffer) > MAX_LINE: raise Violation('JSONL output exceeds 1 MiB')

    def send(self, obj, deadline):
        data = memoryview((json.dumps(obj, allow_nan=False, separators=(',', ':'))+'\n').encode())
        while data:
            if time.monotonic() > deadline: raise Violation('timeout writing query')
            try: data = data[os.write(self.process.stdin.fileno(), data):]
            except BlockingIOError: self.pump(deadline)
            except BrokenPipeError: raise Violation('submission closed stdin') from None

    def receive(self, deadline):
        while b'\n' not in self.buffer: self.pump(deadline)
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        if time.monotonic() > deadline: raise Violation('timeout reading output')
        try: return json.loads(line)
        except (ValueError, UnicodeError, RecursionError): raise Violation('invalid JSONL') from None

    def suspend(self):
        # No processing of the previous query while the grader prepares the next.
        for _ in range(20):
            signal_members(signal.SIGSTOP)
            try:
                if all(p.status() in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE) for p in members()):
                    return
            except psutil.NoSuchProcess: pass
            time.sleep(.001)
        raise Violation('cannot suspend submission family')

    def resume(self):
        signal_members(signal.SIGCONT)

    def close(self):
        signal_members(signal.SIGKILL)
        self.process.wait(timeout=10)
        deadline = time.monotonic()+10
        while list(members()) and time.monotonic() < deadline:
            signal_members(signal.SIGKILL)
            try:
                while os.waitpid(-1, os.WNOHANG)[0]: pass
            except ChildProcessError: pass
            time.sleep(.01)
        if list(members()): raise RuntimeError('Submission descendants survived cleanup')
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr, self.log): stream.close()
