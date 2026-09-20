#!/usr/bin/env python3
"""Linux x86_64 worker: Landlock allowlist + seccomp network/process inspection denial."""

import ctypes as C, os, sys, json

lib = C.CDLL(None, use_errno=True)


def check(x):
    if x < 0:
        raise OSError(C.get_errno(), os.strerror(C.get_errno()))
    return x


class Rules(C.Structure):
    _fields_ = [("handled_access_fs", C.c_uint64)]


class PathRule(C.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", C.c_uint64), ("parent_fd", C.c_int32)]


class Filter(C.Structure):
    _fields_ = [
        ("code", C.c_ushort),
        ("jt", C.c_ubyte),
        ("jf", C.c_ubyte),
        ("k", C.c_uint32),
    ]


class Prog(C.Structure):
    _fields_ = [("len", C.c_ushort), ("filter", C.POINTER(Filter))]


def restrict(read, write, allow_network=False):
    check(lib.prctl(38, 1, 0, 0, 0))
    abi = check(lib.syscall(444, 0, 0, 1))
    if abi < 3:
        raise RuntimeError("Landlock ABI >=3 required")
    mask = (1 << 15) - 1
    rules = Rules(mask)
    fd = check(lib.syscall(444, C.byref(rules), C.sizeof(rules), 0))
    for p, writable in [(x, False) for x in read] + [(x, True) for x in write]:
        if not os.path.exists(p):
            continue
        access = mask if writable else 13  # execute, read_file, read_dir
        if not os.path.isdir(p):
            access &= (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)
        h = os.open(p, os.O_PATH | os.O_CLOEXEC)
        try:
            check(lib.syscall(445, fd, 1, C.byref(PathRule(access, h)), 0))
        finally:
            os.close(h)
    check(lib.syscall(446, fd, 0))
    os.close(fd)
    # Reject non-x86_64, x32, network sockets, ptrace, process_vm*, mount and namespace operations.
    ins = [
        Filter(0x20, 0, 0, 4),
        Filter(0x15, 1, 0, 0xC000003E),
        Filter(0x06, 0, 0, 0x80000000),
        Filter(0x20, 0, 0, 0),
        Filter(0x35, 0, 1, 0x40000000),
        Filter(0x06, 0, 0, 0x00050001),
    ]
    blocked = [101, 165, 166, 272, 308, 310, 311, 321, 304, 425, 426, 427]
    if not allow_network:
        blocked += [41, 53]
    for nr in blocked:
        ins.extend([Filter(0x15, 0, 1, nr), Filter(0x06, 0, 0, 0x00050001)])
    ins.append(Filter(0x06, 0, 0, 0x7FFF0000))
    arr = (Filter * len(ins))(*ins)
    check(lib.prctl(22, 2, C.byref(Prog(len(ins), arr)), 0, 0))


if __name__ == "__main__":
    config = json.loads(sys.argv[1])
    argv = sys.argv[2:]
    restrict(config["read"], config["write"])
    os.execvpe(argv[0], argv, os.environ)
