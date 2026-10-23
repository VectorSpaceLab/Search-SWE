"""Unprivileged worker boundary; labels, scorer, cache and rewards stay outside."""
import ctypes
import errno
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import time
import psutil

UID=10001


def isolate(work):
    libc=ctypes.CDLL(None,use_errno=True)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(100<<30,100<<30))
    if libc.prctl(38,1,0,0,0):raise OSError('no_new_privs')
    abi=libc.syscall(444,0,0,1)
    if abi<3:raise RuntimeError('Landlock ABI >=3 required')
    # ABI3 file execute/read/write/create/remove/rename/truncate protection.
    access=(1<<15)-1
    ruleset=ctypes.c_uint64(access)
    fd=libc.syscall(444,ctypes.byref(ruleset),ctypes.sizeof(ruleset),0)
    if fd<0:raise OSError(ctypes.get_errno(),'landlock_create_ruleset')
    class Rule(ctypes.Structure):
        _pack_=1
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
    try:
        paths=[(str(work),access),('/app/submission',1|4|8),('/task/runtime',1|4|8)]
        paths += [(p,1|4|8) for p in ['/opt','/usr','/lib','/lib64','/etc','/proc','/sys','/run/nvidia'] if Path(p).exists()]
        paths += [('/dev',1|2|4|8)]
        if Path('/dev/shm').is_dir():paths += [('/dev/shm',access)]
        for path,rights in paths:
            parent=os.open(path,os.O_PATH|os.O_CLOEXEC)
            try:
                rule=Rule(rights,parent)
                if libc.syscall(445,fd,1,ctypes.byref(rule),0):raise OSError(ctypes.get_errno(),'landlock_add_rule')
            finally:os.close(parent)
        if libc.syscall(446,fd,0):raise OSError(ctypes.get_errno(),'landlock_restrict_self')
    finally:os.close(fd)
    sec=ctypes.CDLL('libseccomp.so.2')
    sec.seccomp_init.argtypes=[ctypes.c_uint32];sec.seccomp_init.restype=ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    sec.seccomp_load.argtypes=[ctypes.c_void_p];sec.seccomp_release.argtypes=[ctypes.c_void_p]
    class Comparison(ctypes.Structure):
        _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_uint),('a',ctypes.c_uint64),('b',ctypes.c_uint64)]
    sec.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Comparison)]
    ctx=sec.seccomp_init(0x7fff0000)
    try:
        for name in ['ptrace','process_vm_readv','process_vm_writev','pidfd_getfd','unshare','setns','mount','umount2','bpf','perf_event_open','io_uring_setup','open_by_handle_at','name_to_handle_at','mknod','mknodat','reboot','kexec_load','userfaultfd']:
            nr=sec.seccomp_syscall_resolve_name(name.encode())
            if nr>=0 and sec.seccomp_rule_add(ctx,0x50000|errno.EPERM,nr,0):raise RuntimeError('seccomp rule '+name)
        nr=sec.seccomp_syscall_resolve_name(b'clone3')
        if nr>=0 and sec.seccomp_rule_add(ctx,0x50000|errno.ENOSYS,nr,0):raise RuntimeError('clone3 rule')
        conditions=[('clone',Comparison(0,7,flag,flag)) for flag in (0x20000,0x2000000,0x4000000,0x8000000,0x10000000,0x20000000,0x40000000)]
        conditions += [(name,Comparison(0,1,1,0)) for name in ('socket','socketpair')]
        for name,condition in conditions:
            nr=sec.seccomp_syscall_resolve_name(name.encode())
            if nr>=0 and sec.seccomp_rule_add_array(ctx,0x50000|errno.EPERM,nr,1,ctypes.byref(condition)):
                raise RuntimeError('seccomp argument rule')
        if sec.seccomp_load(ctx):raise RuntimeError('seccomp_load')
    finally:sec.seccomp_release(ctx)
    os.setgroups([]);os.setgid(UID);os.setuid(UID);os.chdir(work)


def cleanup():
    if os.environ.get('SEARCH_SWE_VERIFIER_SANDBOX') != '1':
        raise RuntimeError('UID cleanup is restricted to the disposable verifier container')
    for sig in (signal.SIGTERM,signal.SIGKILL):
        for p in psutil.process_iter(['uids']):
            try:
                if p.info['uids'].real==UID:p.send_signal(sig)
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        time.sleep(.1)
    if Path('/dev/shm').is_dir():
        for path in Path('/dev/shm').iterdir():
            try:
                info=path.lstat()
                if info.st_uid!=UID:continue
                if stat.S_ISDIR(info.st_mode):shutil.rmtree(path)
                else:path.unlink()
            except FileNotFoundError:pass
