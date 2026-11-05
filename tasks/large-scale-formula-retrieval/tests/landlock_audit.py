"""Filesystem isolation for the audit role without enabling user namespaces."""

import ctypes, os, platform
from pathlib import Path


def restrict_audit():
    if platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("Audit sandbox requires Linux x86-64")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 1:
        raise RuntimeError("Audit sandbox requires Landlock")
    # ABI 1 supports bits 0..12. Root-owned read-only snapshots and system
    # files also enforce DAC permissions where old kernels lack TRUNCATE rights.
    handled = (1 << (15 if abi >= 3 else 14 if abi >= 2 else 13)) - 1

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class Beneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    attr = Ruleset(handled)
    fd = libc.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")

    def allow(path, rights):
        p = Path(path)
        if not p.exists():
            return
        handle = os.open(p, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = Beneath(rights, handle)
            if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) < 0:
                raise OSError(ctypes.get_errno(), "landlock_add_rule")
        finally:
            os.close(handle)

    try:
        read_dir = (1 << 0) | (1 << 2) | (1 << 3)
        for path in [
            "/usr",
            "/opt",
            "/etc",
            "/lib",
            "/lib64",
            "/bin",
            "/sbin",
            "/sys",
            "/audit",
        ]:
            allow(path, read_dir)
        # Submission code is readable, but direct execution and all writes are denied.
        allow("/app/submission", (1 << 2) | (1 << 3))
        # State/cache belongs solely to this disposable audit user.
        allow("/home/audit", handled)
        allow("/audit/output", handled)
        for path in ["/dev/null", "/dev/zero"]:
            allow(path, (1 << 1) | (1 << 2))
        for path in ["/dev/urandom", "/dev/random"]:
            allow(path, 1 << 2)
        if libc.prctl(38, 1, 0, 0, 0) < 0:
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
        if libc.syscall(446, fd, 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(fd)
