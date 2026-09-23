#!/usr/bin/env python3
"""Keep submission processes offline while the root-side audit has network access."""
import ctypes
import ctypes.util
import errno
import os
import pwd
import socket
import sys


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
    if not command:
        raise SystemExit("missing submission command")
    block_network()
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    os.execvpe(command[0], command, os.environ)
