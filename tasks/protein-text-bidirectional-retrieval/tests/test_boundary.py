"""Run in a disposable task container as root, without host fixture paths."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, '/task/runtime' if Path('/task/runtime').is_dir() else str(Path(__file__).resolve().parents[1] / 'environment/runtime'))
from isolation import UID, isolate


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


if __name__ == '__main__':
    unittest.main()
