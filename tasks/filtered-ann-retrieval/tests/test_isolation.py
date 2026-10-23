"""Real execution boundaries; run as root in the disposable verifier container.

Never run the UID-cleanup checks on the host: they intentionally kill every
process of the container's dedicated `submission` user.
"""
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from grader import Process, check_index_files, check_quality, ensure_owned, run_stage


# Double-fork, leave the launcher's process group and retain a live daemon.
DAEMON = '''
import os, time
from pathlib import Path
read_fd, write_fd = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_fd)
    os.setsid()
    if os.fork():
        os._exit(0)
    (index_dir / ('escape-' + str(os.getpid()) + '.pid')).write_text(str(os.getpid()))
    os.write(write_fd, b'1')
    os.close(write_fd)
    for fd in (0, 1, 2):
        os.close(fd)
    while True:
        time.sleep(1)
os.close(write_fd)
assert os.read(read_fd, 1) == b'1'
os.close(read_fd)
os.waitpid(child, 0)
'''


SYSV_CREATE = '''
import ctypes, json, os
from pathlib import Path
libc = ctypes.CDLL(None, use_errno=True)
libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
libc.shmat.restype = ctypes.c_void_p
libc.shmdt.argtypes = [ctypes.c_void_p]
objects = dict(shm=libc.shmget(0, 4096, 0o1600),
               msg=libc.msgget(0, 0o1600), sem=libc.semget(0, 1, 0o1600))
assert min(objects.values()) >= 0, ctypes.get_errno()
address = libc.shmat(objects['shm'], None, 0)
assert address != ctypes.c_void_p(-1).value, ctypes.get_errno()
ctypes.memmove(address, b'non-file-state', 14)
assert libc.shmdt(address) == 0
if change_owner:
    # IPC_STAT/IPC_SET share ipc_perm's leading key/uid/gid/cuid/cgid fields.
    # Check the native layout before changing ownership; creator stays intact.
    for kind, identifier in objects.items():
        buffer = ctypes.create_string_buffer(512)
        def control(command):
            if kind == 'sem': return libc.semctl(identifier, 0, command, buffer)
            return getattr(libc, kind + 'ctl')(identifier, command, buffer)
        assert control(2) == 0, ctypes.get_errno()
        permissions = (ctypes.c_uint * 5).from_buffer(buffer)
        assert list(permissions)[1:] == [os.getuid(), os.getgid(), os.getuid(), os.getgid()]
        permissions[1] = permissions[2] = 65534
        assert control(1) == 0, ctypes.get_errno()
(index_dir / 'sysv.json').write_text(json.dumps(objects))
'''


SYSV_ABSENT = '''
import ctypes, errno, json
libc = ctypes.CDLL(None, use_errno=True)
libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
libc.shmat.restype = ctypes.c_void_p
objects = json.loads((index_dir / 'sysv.json').read_text())
assert libc.shmat(objects['shm'], None, 0) == ctypes.c_void_p(-1).value
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
buffer = ctypes.create_string_buffer(512)
assert libc.msgctl(objects['msg'], 2, buffer) == -1
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
assert libc.semctl(objects['sem'], 0, 12) == -1
assert ctypes.get_errno() in (errno.EINVAL, errno.EIDRM)
'''


def ipc_rows():
    rows = {}
    for kind, key in (("shm", "shmid"), ("msg", "msqid"), ("sem", "semid")):
        lines = Path(f"/proc/sysvipc/{kind}").read_text().splitlines()
        for line in lines[1:]:
            row = dict(zip(lines[0].split(), line.split(), strict=True))
            rows[kind, int(row[key])] = row
    return rows


def alive(pid):
    try:
        status = Path(f"/proc/{pid}/status").read_text()
    except FileNotFoundError:
        return False
    state = next(line for line in status.splitlines() if line.startswith("State:"))
    threads = next(line for line in status.splitlines() if line.startswith("Threads:"))
    return state.split()[1] not in ("Z", "X") or int(threads.split()[1]) > 1


@unittest.skipUnless(Path("/.dockerenv").exists() and os.geteuid() == 0,
                     "requires an isolated root verifier container")
class ExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(pwd.getpwnam("submission").pw_uid, 10001)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o755)
        self.app = self.root / "app"
        self.app.mkdir(mode=0o755)
        self.index = self.root / "index"
        ensure_owned(self.index, "submission")
        ensure_owned(self.index / "tmp", "submission")

    def process(self, code, service=False):
        return Process([sys.executable, "-c", code], self.app, self.index,
                       self.root / "child.log", "submission", 1, service=service)

    def assert_daemons_dead(self, index):
        for path in index.glob("escape-*.pid"):
            self.assertFalse(alive(int(path.read_text())), str(path))

    def test_sysv_objects_of_dead_creators_cannot_cross_boundaries(self):
        for boundary in ("build", "restart", "relocation", "timeout", "malformed", "exit"):
            for change_owner in (False, True):
                with self.subTest(boundary=boundary, change_owner=change_owner):
                    code = f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n"
                    code += f"change_owner = {change_owner!r}\n" + SYSV_CREATE
                    if boundary != "build":
                        code += "\nimport time\nprint('{\"status\":\"ready\"}', flush=True)\n"
                        if boundary == "malformed":
                            code += "print('invalid JSON', flush=True)\n"
                        code += "raise SystemExit(17)\n" if boundary == "exit" else "time.sleep(30)\n"
                    child = self.process(code, service=boundary != "build")
                    try:
                        if boundary == "build":
                            child.build_wait(10)
                            self.assertEqual(child.proc.wait(timeout=5), 0)
                            self.assertFalse(alive(child.proc.pid))
                        else:
                            self.assertEqual(child.readline(10), {"status": "ready"})
                            if boundary in ("timeout", "malformed", "exit"):
                                error = {"timeout": TimeoutError, "malformed": ValueError,
                                         "exit": RuntimeError}[boundary]
                                with self.assertRaises(error):
                                    child.readline(0.05)
                        objects = json.loads((self.index / "sysv.json").read_text())
                        rows = ipc_rows()
                        for kind, identifier in objects.items():
                            self.assertEqual(int(rows[kind, identifier]["cuid"]), 10001)
                            self.assertEqual(int(rows[kind, identifier]["uid"]),
                                             65534 if change_owner else 10001)
                    finally:
                        child.close()
                    self.assertTrue(set(objects.items()).isdisjoint(ipc_rows()))
                    if boundary == "relocation":
                        self.index.rename(self.root / "relocated-index")
                        self.index = self.root / "relocated-index"
                    probe = self.process(
                        f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n" + SYSV_ABSENT,
                        service=True)
                    try:
                        probe.build_wait(10)
                    finally:
                        probe.close()

    def test_ipc_cleanup_preserves_other_users_objects(self):
        code = f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n"
        code += "change_owner = False\n" + SYSV_CREATE
        subprocess.run([sys.executable, "-c", code], check=True, timeout=10)
        foreign = json.loads((self.index / "sysv.json").read_text())
        (self.index / "sysv.json").unlink()
        try:
            # Owner-only match: created by root, then transferred to submission.
            transferred_code = code.replace("change_owner = False", "change_owner = True")
            transferred_code = transferred_code.replace("permissions[1] = permissions[2] = 65534",
                                                        "permissions[1] = permissions[2] = 10001")
            subprocess.run([sys.executable, "-c", transferred_code], check=True, timeout=10)
            transferred = json.loads((self.index / "sysv.json").read_text())
            for kind, identifier in transferred.items():
                self.assertEqual(int(ipc_rows()[kind, identifier]["cuid"]), 0)
                self.assertEqual(int(ipc_rows()[kind, identifier]["uid"]), 10001)
            (self.index / "sysv.json").unlink()
            child = self.process(code)
            try:
                child.build_wait(10)
            finally:
                child.close()
            self.assertTrue(set(foreign.items()).issubset(ipc_rows()))
            owned = json.loads((self.index / "sysv.json").read_text())
            self.assertTrue(set(owned.items()).isdisjoint(ipc_rows()))
            self.assertTrue(set(transferred.items()).isdisjoint(ipc_rows()))
        finally:
            for kind, identifier in foreign.items():
                subprocess.run(["/usr/bin/ipcrm", {"shm": "-m", "msg": "-q", "sem": "-s"}[kind],
                                str(identifier)], check=True, timeout=5)

    def test_ipc_cleanup_failure_is_not_silently_accepted(self):
        read_text = Path.read_text
        for failure in ("remove_error", "false_success", "timeout", "unreadable", "malformed"):
            with self.subTest(failure=failure):
                code = f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n"
                child = self.process(code + "change_owner = False\n" + SYSV_CREATE)
                try:
                    child.build_wait(10)
                    objects = json.loads((self.index / "sysv.json").read_text())
                    if failure in ("unreadable", "malformed"):
                        def broken_table(path, *args, **kwargs):
                            if str(path) == "/proc/sysvipc/shm":
                                if failure == "unreadable":
                                    raise PermissionError("IPC table unavailable")
                                return "unexpected columns\n"
                            return read_text(path, *args, **kwargs)
                        fault = patch.object(Path, "read_text", broken_table)
                        expected = PermissionError if failure == "unreadable" else RuntimeError
                    elif failure == "timeout":
                        fault = patch("grader.subprocess.run",
                                      side_effect=subprocess.TimeoutExpired("ipcrm", 5))
                        expected = subprocess.TimeoutExpired
                    else:
                        fault = patch("grader.subprocess.run", return_value=SimpleNamespace(
                            returncode=int(failure == "remove_error"), stderr="injected failure"))
                        expected = RuntimeError
                    with fault, self.assertRaises(expected):
                        child.close()
                    self.assertTrue(set(objects.items()).issubset(ipc_rows()))
                finally:
                    # Real cleanup after fault injection, inside this private IPC namespace.
                    child.close()

    def test_detached_children_die_after_build_phase_and_error(self):
        for boundary in ("build", "phase", "timeout", "malformed", "exit"):
            with self.subTest(boundary=boundary):
                code = f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n" + DAEMON
                if boundary != "build":
                    code += "\nimport json, sys\nprint(json.dumps({'status':'ready'}), flush=True)\n"
                    if boundary == "malformed":
                        code += "print('invalid JSON', flush=True)\ntime.sleep(30)\n"
                    elif boundary == "exit":
                        code += "raise SystemExit(17)\n"
                    else:
                        code += "time.sleep(30)\n"
                child = self.process(code, service=boundary != "build")
                try:
                    if boundary == "build":
                        child.build_wait(10)
                    else:
                        self.assertEqual(child.readline(10), {"status": "ready"})
                        if boundary in ("timeout", "malformed", "exit"):
                            expected = {"timeout": TimeoutError, "malformed": ValueError,
                                        "exit": RuntimeError}[boundary]
                            with self.assertRaises(expected):
                                child.readline(0.1)
                    self.assertTrue(any(alive(int(p.read_text())) for p in self.index.glob("escape-*.pid")))
                finally:
                    child.close()
                self.assert_daemons_dead(self.index)

    def test_zombie_leader_with_live_thread_is_still_killed(self):
        daemon = DAEMON.replace("while True:\n        time.sleep(1)", """import ctypes, platform, threading
    threading.Thread(target=time.sleep, args=(30,)).start()
    # SYS_exit exits only this thread; the detached process still has a worker.
    ctypes.CDLL(None).syscall(60 if platform.machine() == 'x86_64' else 93, 0)""")
        child = self.process(f"index_dir = __import__('pathlib').Path({str(self.index)!r})\n" + daemon)
        try:
            child.build_wait(10)
            pid = int(next(self.index.glob("escape-*.pid")).read_text())
            deadline = time.monotonic() + 5
            while "State:\tZ" not in Path(f"/proc/{pid}/status").read_text():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            self.assertTrue(alive(pid))
        finally:
            child.close()
        self.assert_daemons_dead(self.index)

    def test_aliases_and_canonical_corpus_denied_but_relocated_index_loads(self):
        corpus = self.root / "corpus"
        corpus.mkdir()
        with (corpus / "vectors.u8bin").open("wb") as handle:
            np.array([3, 1], dtype="<u4").tofile(handle)
            np.array([0, 1, 4], dtype=np.uint8).tofile(handle)
        with (corpus / "metadata.spmat").open("wb") as handle:
            np.array([3, 1, 3], dtype="<i8").tofile(handle)
            np.arange(4, dtype="<i8").tofile(handle)
            np.zeros(3, dtype="<i4").tofile(handle)
            np.ones(3, dtype="<f4").tofile(handle)
        original_modes = {p.name: p.stat().st_mode for p in corpus.iterdir()}
        aliases = self.root / "build-input"
        aliases.mkdir()
        for p in corpus.iterdir():
            (aliases / p.name).symlink_to(p)
        retired = self.root / "work/retrieval/retired-build-input"
        forbidden = [str(parent / name) for parent in (corpus, aliases, retired)
                     for name in ("vectors.u8bin", "metadata.spmat")]
        # A link under allowed code, and proc's root magic link, must not help.
        (self.app / "corpus-link").symlink_to(corpus, target_is_directory=True)
        forbidden += [str(self.app / "corpus-link/vectors.u8bin"),
                      "/proc/self/root" + str(corpus / "vectors.u8bin")]
        (self.app / "forbidden.json").write_text(json.dumps(forbidden))
        build = '''import argparse, faiss, numpy as np
from pathlib import Path
p=argparse.ArgumentParser()
for name in ('vectors','metadata','index-dir'): p.add_argument('--'+name)
a=p.parse_args()
assert Path(a.metadata).read_bytes()
vectors=np.fromfile(a.vectors,dtype=np.uint8,offset=8).reshape(3,1).astype('float32')
index_dir=Path(a.index_dir)
idx=faiss.IndexHNSWFlat(1,2)
idx.add(vectors)
faiss.write_index(idx,str(index_dir/'index.faiss'))
''' + DAEMON + "\nchange_owner = False\n" + SYSV_CREATE
        serve = '''import argparse, json, sys, faiss, numpy as np
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--index-dir');p.add_argument('--serve',action='store_true')
a=p.parse_args();index_dir=Path(a.index_dir)
for path in json.loads(Path('forbidden.json').read_text()):
    try:
        with open(path,'rb') as handle: handle.read(1)
    except (PermissionError,FileNotFoundError): pass
    else: raise AssertionError('source still readable: '+path)
idx=faiss.read_index(str(index_dir/'index.faiss'))
# This three-vector fixture needs one search thread, not an eight-thread team.
faiss.omp_set_num_threads(1)
idx.search(np.zeros((1,1),dtype='float32'),2)
''' + DAEMON + "\nchange_owner = True\n" + SYSV_CREATE + '''
print(json.dumps({'status':'ready'}),flush=True)
for line in sys.stdin:
    q=json.loads(line)
    distances, ids=idx.search(np.array([q['vector']],dtype='float32'),q['k'])
    print(json.dumps({'query_id':q['query_id'],'results':[{'doc_id':int(i)} for i in ids[0]]}),flush=True)
'''
        for name, code in (("build.sh", build), ("run.sh", serve)):
            path = self.app / name
            path.write_text(f"#!{sys.executable}\n" + code)
            path.chmod(0o555)
        queries = [{"query_id": str(i), "vector": [0], "filter": {"all": [0]}, "k": 2}
                   for i in range(25)]
        gold = [{"query_id": str(i), "eligible_count": 3, "distances": [0.0, 1.0],
                 "group": "synthetic"} for i in range(25)]
        for name, rows in (("queries.jsonl", queries), ("gold.jsonl", gold)):
            (self.root / name).write_text("\n".join(map(json.dumps, rows)))
        args = SimpleNamespace(app=self.app, work_dir=self.root / "work",
                               run_as="submission", report=self.root / "evaluation.json")
        starts = []
        test = self

        class ObservedProcess(Process):
            def __init__(self, command, app, work, *args, **kwargs):
                # Observe the real orchestration; every subprocess still runs.
                test.assert_daemons_dead(work)
                test.assertFalse(any(10001 in (int(row["uid"]), int(row["cuid"]))
                                     for row in ipc_rows().values()))
                starts.append(work.name)
                super().__init__(command, app, work, *args, **kwargs)

        with patch("grader.Process", ObservedProcess):
            report = run_stage(args, "retrieval", aliases,
                               self.root / "queries.jsonl", self.root / "gold.jsonl")
        self.assertEqual(check_quality(report), 1.0, report)
        self.assertEqual(report["request_count_including_reload_checks"], 50)
        self.assertEqual(starts, ["index", "index", "restored-index"])
        self.assert_daemons_dead(args.work_dir / "retrieval/restored-index")
        self.assertFalse(any(10001 in (int(row["uid"]), int(row["cuid"]))
                             for row in ipc_rows().values()))
        self.assertEqual(original_modes, {p.name: p.stat().st_mode for p in corpus.iterdir()})

    def test_special_index_entries_rejected_without_opening_them(self):
        nested = self.index / "nested"
        nested.mkdir()
        (nested / "regular").write_bytes(b"state")
        check_index_files(self.index)
        for kind in ("fifo", "socket", "character", "block", "symlink"):
            with self.subTest(kind=kind):
                path = nested / "special"
                sock = None
                try:
                    if kind == "fifo":
                        os.mkfifo(path)
                    elif kind == "socket":
                        sock = socket.socket(socket.AF_UNIX)
                        sock.bind(str(path))
                    elif kind in ("character", "block"):
                        mode = stat.S_IFCHR if kind == "character" else stat.S_IFBLK
                        os.mknod(path, mode | 0o600, os.makedev(1, 3))
                    else:
                        path.symlink_to(nested, target_is_directory=True)
                    started = time.monotonic()
                    with self.assertRaises(ValueError):
                        check_index_files(self.index)
                    self.assertLess(time.monotonic() - started, 1.0)
                finally:
                    if sock is not None:
                        sock.close()
                    path.unlink(missing_ok=True)
        link = self.root / "index-link"
        link.symlink_to(self.index, target_is_directory=True)
        with self.assertRaises(ValueError):
            check_index_files(link)
        with self.assertRaises(ValueError):
            check_index_files(nested / "regular")


if __name__ == "__main__":
    unittest.main()
