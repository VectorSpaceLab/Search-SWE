"""Kernel filesystem, device, syscall and UID boundary for strategy processes."""
import ctypes
import errno
import os
from pathlib import Path
import resource
import signal
import time
import psutil

UID = 10001


class Comparison(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int),
                ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]


def write_boundary(work):
    """Landlock ABI >=3: all descendants can write only inside their work dir."""
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError('Linux Landlock ABI >=3 is required')
    # Handle all write/create/delete/rename/truncate operations; reads use DAC.
    access = 2 | sum(1 << i for i in range(4, 15))
    ruleset = ctypes.c_uint64(access)
    fd = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'landlock_create_ruleset')
    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int32)]
    try:
        for path, rights in ((work, access), ('/dev/null', 2)):
            parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(rights, parent)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), 'landlock_add_rule')
            finally:
                os.close(parent)
        if libc.syscall(446, fd, 0):
            raise OSError(ctypes.get_errno(), 'landlock_restrict_self')
    finally:
        os.close(fd)


def isolate(work, cpus):
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (40 << 30, 40 << 30))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), 'no_new_privs')
    write_boundary(work)
    sec = ctypes.CDLL('libseccomp.so.2')
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(Comparison)]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    context = sec.seccomp_init(0x7fff0000)
    if not context:
        raise RuntimeError('seccomp_init failed')
    try:
        blocked = ('ptrace', 'process_vm_readv', 'process_vm_writev', 'pidfd_getfd',
                   'unshare', 'setns', 'mount', 'umount2', 'bpf', 'perf_event_open',
                   'io_uring_setup', 'open_by_handle_at', 'name_to_handle_at',
                   'mknod', 'mknodat', 'sched_setaffinity',
                   'reboot', 'kexec_load', 'userfaultfd')
        for name in blocked:
            nr = sec.seccomp_syscall_resolve_name(name.encode())
            if nr >= 0 and sec.seccomp_rule_add(context, 0x50000 | errno.EPERM, nr, 0):
                raise RuntimeError('seccomp rule failed: ' + name)
        # Modern libc falls back to clone for threads when clone3 is ENOSYS.
        nr = sec.seccomp_syscall_resolve_name(b'clone3')
        if nr >= 0 and sec.seccomp_rule_add(context, 0x50000 | errno.ENOSYS, nr, 0):
            raise RuntimeError('clone3 rule failed')
        # Deny each namespace flag, rather than requiring all flags together.
        conditions = [('clone', Comparison(0, 7, flag, flag))
                      for flag in (0x20000, 0x2000000, 0x4000000, 0x8000000,
                                   0x10000000, 0x20000000, 0x40000000)]
        conditions += [(name, Comparison(0, 1, 1, 0)) for name in ('socket', 'socketpair')]
        # Permit terminal/descriptor ioctls (notably FIOCLEX used by CPython's
        # script loader). NVIDIA/UVM control requests are outside this range.
        conditions += [('ioctl', Comparison(1, 2, 0x5400, 0)),
                       ('ioctl', Comparison(1, 6, 0x54ff, 0))]
        for name, condition in conditions:
            nr = sec.seccomp_syscall_resolve_name(name.encode())
            if nr >= 0 and sec.seccomp_rule_add_array(context, 0x50000 | errno.EPERM,
                                                    nr, 1, ctypes.byref(condition)):
                raise RuntimeError('seccomp argument rule failed: ' + name)
        if sec.seccomp_load(context):
            raise RuntimeError('seccomp_load failed')
    finally:
        sec.seccomp_release(context)
    os.setgroups([])
    os.setgid(UID)
    os.setuid(UID)
    os.chdir(work)


def members():
    result = []
    for p in psutil.process_iter(['uids']):
        try:
            if p.info['uids'].real == UID:
                result.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def signal_all(sig):
    for p in members():
        try:
            p.send_signal(sig)
        except psutil.NoSuchProcess:
            pass


def freeze(deadline):
    while time.monotonic() < deadline:
        signal_all(signal.SIGSTOP)
        processes = members()
        try:
            if processes and all(p.status() in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE)
                                 for p in processes):
                # Stopped parents cannot produce new children after this scan.
                return
        except psutil.NoSuchProcess:
            continue
        time.sleep(.001)
    raise TimeoutError('Could not quiesce the complete strategy process tree')


def cleanup():
    signal_all(signal.SIGKILL)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            pid = 0
        if not pid:
            if not members():
                break
            time.sleep(.005)
    if members():
        raise RuntimeError('Submission processes survived cleanup')


def protect():
    if os.getuid() != 0:
        raise RuntimeError('The trusted supervisor must run as root')
    if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0):
        raise RuntimeError('Cannot enable subreaper')
    for top in Path('/dev').glob('nvidia*'):
        for path in ([top] if not top.is_dir() else top.rglob('*')):
            if path.is_dir():
                continue
            os.chown(path, 0, 0)
            os.chmod(path, 0o600)


def bytes_used(root, deadline):
    size = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        if time.monotonic() > deadline:
            raise TimeoutError('Storage audit timed out')
        for name in names:
            try:
                p = Path(base) / name
                if not p.is_symlink():
                    s = p.stat()
                    size += max(s.st_size, 512 * s.st_blocks)
            except FileNotFoundError:
                pass
    return size
