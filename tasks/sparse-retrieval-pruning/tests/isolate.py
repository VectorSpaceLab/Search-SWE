#!/usr/bin/env python3
"""Linux-only launcher: drop privileges and restrict candidate state access.

Requires Landlock ABI >= 1 and seccomp filters; missing confinement fails closed.
The outer verifier container supplies CPU, memory, PID and network limits.
"""

import ctypes
import errno
import os
import resource
import sys
from pathlib import Path

UID = GID = 10001
EXECUTE, WRITE, READ, READ_DIR = 1, 2, 4, 8
REFER, TRUNCATE = 1 << 13, 1 << 14
ALL = (1 << 15) - 1
LIBRARIES = ["/lib", "/lib64", "/usr/lib", "/usr/lib64", "/etc/ld.so.cache"]


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]


class SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(SockFilter))]


def restrict_persistent_state():
    """Disallow state that can outlive a candidate without being index bytes.

    Applied before exec in *every* candidate phase and inherited by children.
    Anonymous mappings and file-backed mmap still work.
    Syscall numbers use Linux arch/x86/entry/syscalls/syscall_64.tbl; reject
    other ABIs, including x32 (which shares the x86_64 audit architecture).
    """
    if os.uname().machine != "x86_64":
        raise RuntimeError("This pinned sparse runtime supports Linux x86_64")
    denied = [
        29, 30, 31, 67,           # shmget, shmat, shmctl, shmdt
        64, 65, 66, 220,          # semget, semop, semctl, semtimedop
        68, 69, 70, 71,           # msgget, msgsnd, msgrcv, msgctl
        240, 241, 242, 243, 244, 245,  # POSIX message queues
        248, 249, 250,            # add_key, request_key, keyctl
        # Landlock does not mediate xattr reads, including on outside paths.
        *range(188, 200),         # set/get/list/remove xattr, l* and f* forms
        425, 426, 427,            # io_uring can issue xattr operations indirectly
        463, 464, 465, 466,       # *xattrat variants (Linux >= 6.13)
    ]
    deny = 0x00050000 | errno.EPERM  # SECCOMP_RET_ERRNO
    instructions = [
        (0x20, 0, 0, 4),           # BPF_LD W ABS: seccomp_data.arch
        (0x15, 1, 0, 0xC000003E),  # BPF_JMP JEQ: AUDIT_ARCH_X86_64
        (0x06, 0, 0, 0x80000000),  # SECCOMP_RET_KILL_PROCESS for other ABIs
        (0x20, 0, 0, 0),           # seccomp_data.nr
        (0x45, 0, 1, 0x40000000),  # BPF_JMP JSET: __X32_SYSCALL_BIT
        (0x06, 0, 0, deny),
    ]
    for number in sorted(denied):
        instructions += [(0x15, 0, 1, number), (0x06, 0, 0, deny)]
    instructions.append((0x06, 0, 0, 0x7FFF0000))  # SECCOMP_RET_ALLOW
    filters = (SockFilter * len(instructions))(*(SockFilter(*i) for i in instructions))
    program = SockFprog(len(filters), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "Cannot set no_new_privs")
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:  # PR_SET_SECCOMP, FILTER
        raise OSError(ctypes.get_errno(), "Cannot restrict persistent IPC and xattrs")


def confine(rules):
    if os.uname().machine != "x86_64":
        raise RuntimeError("This pinned sparse runtime supports Linux x86_64")
    libc = ctypes.CDLL(None, use_errno=True)
    def call(number, *args):
        result = libc.syscall(ctypes.c_long(number), *args)
        if result < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return result
    abi = call(444, 0, 0, 1)
    if abi < 1:
        raise RuntimeError(f"Landlock ABI >= 1 required; available ABI: {abi}")
    handled = (1 << 13) - 1
    if abi >= 2:
        handled |= REFER
    if abi >= 3:
        handled |= TRUNCATE
    # ABI 1/2 do not mediate truncate. Search files and directories are also
    # root-owned and mode 0444/0555; all prior candidate-writable areas are
    # inaccessible by ordinary permissions before search starts.
    attr = Ruleset(handled)
    fd = call(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    try:
        merged = {}
        for filename, access in rules:
            access &= handled
            path = Path(filename).resolve(strict=True)
            if not path.is_dir():
                access &= EXECUTE | WRITE | READ | TRUNCATE
            merged[path] = merged.get(path, 0) | access
        for path, access in merged.items():
            parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, parent)
                call(445, fd, 1, ctypes.byref(rule), 0)
            finally:
                os.close(parent)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise OSError(ctypes.get_errno(), "Cannot set no_new_privs")
        call(446, fd, 0)
    finally:
        os.close(fd)


def launch(command, readable, writable, cwd, cpu):
    rules = [(p, READ | READ_DIR | EXECUTE) for p in
             ["/usr", "/opt/conda", "/opt/java", "/bin", "/lib", "/lib64", "/etc", "/sys/devices/system/cpu"]
             if Path(p).exists()]
    rules += [(str(p), READ | READ_DIR | EXECUTE) for p in readable]
    rules += [(str(p), ALL) for p in writable]
    rules += [("/dev/null", READ | WRITE), ("/dev/urandom", READ)]
    os.sched_setaffinity(0, {cpu})
    os.setgroups([])
    os.setgid(GID)
    os.setuid(UID)
    os.chdir(cwd)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # RLIMIT_NPROC counts this UID across containers without user namespaces.
    # An unrelated verifier can otherwise prevent even a serial Bash fork.
    # Use the container's PID cgroup cap; threads and Python workers are
    # independently restricted by seccomp and the invocation monitor.
    resource.setrlimit(resource.RLIMIT_FSIZE, (80 << 30, 80 << 30))
    confine(rules)
    restrict_persistent_state()
    # No socket IPC (including abstract Unix sockets) can carry answers between rounds.
    # Deny new threads in the kernel; serial shell wrapper children remain possible.
    sec = ctypes.CDLL("libseccomp.so.2")
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                    ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]
    sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(Comparison)]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError("seccomp init failed")
    try:
        for name in ("socket", "socketpair", "sched_setaffinity", "ptrace", "process_vm_readv", "process_vm_writev"):
            nr = sec.seccomp_syscall_resolve_name(name.encode())
            if nr >= 0 and sec.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, nr, 0):
                raise RuntimeError("seccomp rule failed")
        nr = sec.seccomp_syscall_resolve_name(b"clone3")
        if nr >= 0 and sec.seccomp_rule_add(ctx, 0x50000 | errno.ENOSYS, nr, 0):
            raise RuntimeError("seccomp clone3 rule failed")
        condition = Comparison(0, 7, 0x10000, 0x10000)  # clone flags & CLONE_THREAD
        nr = sec.seccomp_syscall_resolve_name(b"clone")
        if sec.seccomp_rule_add_array(ctx, 0x50000 | errno.EPERM, nr, 1, ctypes.byref(condition)):
            raise RuntimeError("seccomp thread rule failed")
        if sec.seccomp_load(ctx):
            raise RuntimeError("seccomp load failed")
    finally:
        sec.seccomp_release(ctx)
    os.execvpe(command[0], command, os.environ)
