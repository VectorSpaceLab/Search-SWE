#!/usr/bin/env python3
"""Keep submissions offline and services confined to persisted runtime state."""
import ctypes
import ctypes.util
import errno
import os
from pathlib import Path
import platform
import pwd
import socket
import sys


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def restrict_service_files(app, index):
    """Landlock follows resolved files, so aliases cannot reopen the corpus.

    Require ABI 3 (Linux 6.2+) for truncate protection. Fail closed if the
    kernel/container cannot enforce this policy; never silently run unrestricted.
    Rules survive exec/fork and need neither mounts nor privileged containers.
    """
    if platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("unsupported architecture for Landlock syscall numbers")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long

    def syscall(number, *args):
        result = libc.syscall(ctypes.c_long(number), *args)
        if result < 0:
            error = ctypes.get_errno()
            raise OSError(error, "Landlock service isolation: " + os.strerror(error))
        return result

    abi = syscall(444, ctypes.c_void_p(), ctypes.c_size_t(0), ctypes.c_uint(1))
    if abi < 3:
        raise RuntimeError("Landlock ABI >= 3 is required for service isolation")
    execute, write, read, read_dir = (1 << bit for bit in range(4))
    truncate = 1 << 14
    handled = (1 << 15) - 1
    readonly = execute | read | read_dir
    # Runtime state may contain regular files/directories, never special files.
    writable = readonly | write | truncate | sum(1 << bit for bit in (4, 5, 7, 8, 13))
    ruleset = RulesetAttr(handled)
    ruleset_fd = syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    try:
        def allow(path, access):
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                if not Path(path).is_dir():
                    access &= execute | read | write | truncate
                rule = PathBeneathAttr(access, fd)
                syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0)
            finally:
                os.close(fd)

        allow(app, readonly)
        allow(index, writable)
        # Interpreter, shared libraries and read-only system configuration.
        # Do not allow /task, /tmp, /home, /dev/shm or a common ancestor of index.
        for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt/conda",
                     "/etc/ld.so.cache", "/etc/localtime", "/etc/nsswitch.conf",
                     "/etc/passwd", "/etc/group", "/proc/self", "/proc/cpuinfo",
                     "/proc/meminfo", "/sys/devices/system/cpu"):
            if Path(path).exists():
                allow(path, readonly)
        for path in ("/dev/null", "/dev/zero", "/dev/random", "/dev/urandom"):
            allow(path, read | write | truncate)
        # block_network() has already set no_new_privs, as required by Landlock.
        syscall(446, ruleset_fd, 0)
    finally:
        os.close(ruleset_fd)


class ArgCompare(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]


def block_network():
    library = ctypes.util.find_library("seccomp")
    if not library:
        raise RuntimeError("libseccomp is required to isolate the submission")
    seccomp = ctypes.CDLL(library)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                              ctypes.c_int, ctypes.c_uint,
                                              ctypes.POINTER(ArgCompare)]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    # Default allow; socket/socketpair may only create local Unix-domain sockets.
    context = seccomp.seccomp_init(0x7FFF0000)
    if not context:
        raise RuntimeError("could not initialize seccomp")
    try:
        condition = ArgCompare(0, 1, socket.AF_UNIX, 0)  # SCMP_CMP_NE
        for name in (b"socket", b"socketpair"):
            number = seccomp.seccomp_syscall_resolve_name(name)
            if number < 0 or seccomp.seccomp_rule_add_array(
                    context, 0x00050000 | errno.EPERM, number, 1,
                    ctypes.byref(condition)) != 0:
                raise RuntimeError("could not install socket restriction")
        # libseccomp enables no_new_privs; the filter survives exec and fork.
        if seccomp.seccomp_load(context) != 0:
            raise RuntimeError("could not activate submission network restriction")
    finally:
        seccomp.seccomp_release(context)


if __name__ == "__main__":
    user = pwd.getpwnam(sys.argv[1])
    command = sys.argv[2:]
    service_paths = None
    if command[:1] == ["--service"]:
        service_paths = command[1:3]
        command = command[3:]
    if not command:
        raise SystemExit("missing submission command")
    block_network()
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    if service_paths is not None:
        restrict_service_files(*service_paths)
    os.execvpe(command[0], command, os.environ)
