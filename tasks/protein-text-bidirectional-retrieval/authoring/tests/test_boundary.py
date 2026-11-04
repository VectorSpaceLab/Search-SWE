"""Run in a disposable task container as root, without host fixture paths."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import ctypes
import os
import subprocess
import tempfile
import unittest

sys.path.insert(0, '/task/runtime' if Path('/task/runtime').is_dir() else str(TASK_ROOT / 'environment/runtime'))
from isolation import UID, cleanup, isolate, submission_sysv_ipc


@unittest.skipUnless(Path('/opt/conda/bin/python').exists() and Path('/task/runtime').is_dir(), 'container kernel checks')
class BoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p in ['/task/models', '/task/public', '/app/submission', '/tests']:
            Path(p).mkdir(parents=True, exist_ok=True)
        Path('/tests/hidden-sentinel').write_text('hidden')
        Path('/tests').chmod(0o700)
        Path('/app/submission/readable.txt').write_text('public')
        Path('/app/submission/readable.txt').chmod(0o444)

    def code(self, code):
        with tempfile.TemporaryDirectory(dir='/app') as path:
            work = Path(path); os.chown(work, UID, UID)
            result = subprocess.run(['/opt/conda/bin/python', '-c', code], capture_output=True, text=True,
                                    timeout=20, preexec_fn=lambda: isolate(work),
                                    env=dict(os.environ,TMPDIR=str(work),HOME=str(work)))
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

    def test_hidden_and_reward_denied(self):
        self.assertEqual(self.code("\nfor p in ['/tests/hidden-sentinel','/logs/verifier/reward.txt']:\n try: open(p).read();print('leak')\n except PermissionError: print('denied')\n except FileNotFoundError: print('denied')"), 'denied\ndenied')

    def test_scratch_and_public_readable(self):
        self.assertEqual(self.code("from pathlib import Path;Path('scratch').write_text('ok');print(Path('/app/submission/readable.txt').read_text())"), 'public')

    def test_network_denied(self):
        self.assertEqual(self.code("import socket\ntry: socket.socket(socket.AF_INET,socket.SOCK_STREAM);print('leak')\nexcept PermissionError: print('denied')"), 'denied')

    def test_cannot_regain_root(self):
        self.assertEqual(self.code("import os\ntry: os.setuid(0);print('root')\nexcept PermissionError: print(os.getuid())"), '10001')

    def test_descendant_keeps_boundary(self):
        self.assertEqual(self.code("import subprocess\np=subprocess.run(['/opt/conda/bin/python','-c',\"open('/tests/hidden-sentinel').read()\"],capture_output=True);print(p.returncode != 0)"), 'True')

    def test_torch_cpu_dataloader_subprocesses(self):
        self.assertEqual(self.code("import torch\nfrom torch.utils.data import DataLoader\nprint(sum(int(x.sum()) for x in DataLoader(torch.arange(16),batch_size=4,num_workers=2)))"), '120')

    def test_shared_memory_removed_between_groups(self):
        from isolation import cleanup
        self.code("from pathlib import Path\nPath('/dev/shm/task-boundary-sentinel').write_text('candidate state')")
        self.assertTrue(Path('/dev/shm/task-boundary-sentinel').exists())
        cleanup()
        self.assertFalse(Path('/dev/shm/task-boundary-sentinel').exists())

    def test_sysv_objects_removed_without_removing_supervisor_objects(self):
        # All three IPC families can outlive their creator. Ordinary use within
        # a phase must work, but the next isolated worker must not inherit them.
        native = ctypes.CDLL(None, use_errno=True)
        root_ids = [native.shmget(0, 4096, 0o1600), native.msgget(0, 0o1600),
                    native.semget(0, 1, 0o1600)]
        self.assertTrue(all(identifier >= 0 for identifier in root_ids))
        try:
            self.code("""
import ctypes
libc = ctypes.CDLL(None, use_errno=True)
ids = [libc.shmget(0, 4096, 0o1600), libc.msgget(0, 0o1600), libc.semget(0, 1, 0o1600)]
assert all(identifier >= 0 for identifier in ids), ctypes.get_errno()
libc.shmat.restype = ctypes.c_void_p
libc.shmdt.argtypes = [ctypes.c_void_p]
address = libc.shmat(ids[0], None, 0)
assert address != ctypes.c_void_p(-1).value
ctypes.memmove(address, b'candidate-state\\0', 16)
assert ctypes.string_at(address) == b'candidate-state'
assert libc.shmdt(address) == 0
""")
            objects = submission_sysv_ipc()
            self.assertEqual({kind for kind, _ in objects}, {'shm', 'msg', 'sem'})
            cleanup()
            self.assertEqual(submission_sysv_ipc(), [])
            self.code(f"""
import ctypes
libc = ctypes.CDLL(None, use_errno=True)
libc.shmat.restype = ctypes.c_void_p
for kind, identifier in {objects!r}:
    if kind == 'shm':
        assert libc.shmat(identifier, None, 0) == ctypes.c_void_p(-1).value
    elif kind == 'msg':
        assert libc.msgctl(identifier, 2, ctypes.create_string_buffer(1024)) == -1
    else:
        assert libc.semctl(identifier, 0, 12) == -1
""")
            for kind, identifier in zip(['shm', 'msg', 'sem'], root_ids):
                rows = Path('/proc/sysvipc', kind).read_text().splitlines()[1:]
                self.assertIn(identifier, {int(row.split()[1]) for row in rows})
        finally:
            native.shmctl(root_ids[0], 0, None)
            native.msgctl(root_ids[1], 0, None)
            native.semctl(root_ids[2], 0, 0)
            cleanup()


if __name__ == '__main__':
    unittest.main()
