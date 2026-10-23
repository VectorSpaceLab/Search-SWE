"""Kernel restrictions applied before importing any submitted module."""
import ctypes
import errno
import os
from pathlib import Path
import resource
import signal
import time

import psutil

UID = 10001


def isolate(work):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 30, 64 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError("Cannot enable no_new_privs")
    if libc.syscall(444, 0, 0, 1) < 3:
        raise RuntimeError("Landlock ABI 3 or newer is required")
    all_access = (1 << 15) - 1
    ruleset = ctypes.c_uint64(all_access)
    fd = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")

    class Rule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    read_access = 1 | 4 | 8
    paths = [(str(work), all_access), ("/dev", 1 | 2 | 4 | 8)]
    # CUDA names its threads by opening /proc/self/task/<tid>/comm for writing.
    # Procfs DAC and dropped credentials restrict writes to the submission's own
    # processes, including subsequently spawned GPU workers. Grader UID is root.
    paths.append(("/proc", read_access | 2 | (1 << 14)))
    if Path("/dev/shm").exists():
        paths.append(("/dev/shm", all_access))
    paths += [(p, read_access) for p in (
        "/app/submission", "/task/library", "/task/models", "/task/runtime", "/task/dev", "/task/train",
        "/opt", "/usr", "/lib", "/lib64", "/etc", "/sys", "/run/nvidia",
    ) if Path(p).exists()]
    try:
        for path, rights in paths:
            parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = Rule(rights, parent)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), "landlock_add_rule")
            finally:
                os.close(parent)
        if libc.syscall(446, fd, 0):
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(fd)

    sec = ctypes.CDLL("libseccomp.so.2")
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]

    class Comparison(ctypes.Structure):
        _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_uint),
                    ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]

    sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(Comparison)]
    context = sec.seccomp_init(0x7FFF0000)
    if not context:
        raise RuntimeError("Cannot create seccomp context")
    try:
        denied = ("ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd",
                  "unshare", "setns", "mount", "umount2", "bpf", "perf_event_open",
                  "io_uring_setup", "open_by_handle_at", "name_to_handle_at", "mknod",
                  "mknodat", "reboot", "kexec_load", "userfaultfd")
        for name in denied:
            number = sec.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and sec.seccomp_rule_add(context, 0x50000 | errno.EPERM, number, 0):
                raise RuntimeError("Cannot restrict " + name)
        number = sec.seccomp_syscall_resolve_name(b"clone3")
        if number >= 0 and sec.seccomp_rule_add(context, 0x50000 | errno.ENOSYS, number, 0):
            raise RuntimeError("Cannot restrict clone3")
        conditions = [("clone", Comparison(0, 7, flag, flag)) for flag in (
            0x20000, 0x2000000, 0x4000000, 0x8000000, 0x10000000, 0x20000000, 0x40000000)]
        # Only AF_UNIX sockets are needed for local workers; CUDA still uses ioctl.
        conditions += [(name, Comparison(0, 1, 1, 0)) for name in ("socket", "socketpair")]
        for name, condition in conditions:
            number = sec.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and sec.seccomp_rule_add_array(
                    context, 0x50000 | errno.EPERM, number, 1, ctypes.byref(condition)):
                raise RuntimeError("Cannot restrict arguments of " + name)
        if sec.seccomp_load(context):
            raise RuntimeError("Cannot load seccomp restrictions")
    finally:
        sec.seccomp_release(context)
    os.setgroups([])
    os.setgid(UID)
    os.setuid(UID)
    # setuid clears dumpability, making even own procfs environment/comm entries
    # root-owned. Restore ordinary nonroot-process behavior for CUDA.
    if libc.prctl(4, 1, 0, 0, 0):
        raise OSError("Cannot restore submission procfs ownership")
    os.chdir(work)


def cleanup():
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for process in psutil.process_iter(["uids"]):
            try:
                if process.info["uids"].real == UID:
                    process.send_signal(sig)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(.1)
