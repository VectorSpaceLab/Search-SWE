"""Run explicitly in a disposable verifier-style Docker container."""
import os
import ctypes
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(os.environ.get("MOLECULAR_BOUNDARY_TEST") == "1", "disposable container test")
class BoundaryTests(unittest.TestCase):
    def test_hidden_files_rewards_network_and_process_boundary(self):
        private = Path("/tests/private-probe")
        private.write_text("hidden-labels")
        Path("/tests").chmod(0o700)
        work = Path("/app/boundary-work")
        work.mkdir()
        work.chmod(0o700)
        os.chown(work, 10001, 10001)
        submission = Path("/app/submission")
        submission.mkdir(exist_ok=True)
        (submission / "retriever.py").write_text("# immutable submission\n")
        submission.chmod(0o555)
        (submission / "retriever.py").chmod(0o444)
        code = r'''
import ctypes, errno, os, socket, sys
from pathlib import Path
from isolation import isolate
assert sys.stdin.readline().strip() == 'probe'
isolate('/app/boundary-work')
assert os.getuid() == 10001
Path('/app/boundary-work/allowed').write_text('ok')
for path, mode in [('/tests/private-probe','r'),('/logs/verifier/reward.txt','w'),
                   ('/app/submission/retriever.py','w'),('/tmp/escape','w'),
                   ('/var/tmp/escape','w'),('/proc/%d/environ' % os.getppid(),'r')]:
    try:
        with open(path, mode): pass
    except (PermissionError, FileNotFoundError): pass
    else: raise AssertionError('Unexpected access to '+path)
try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except PermissionError: pass
else: raise AssertionError('TCP socket allowed')
unix=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);unix.close()
libc=ctypes.CDLL(None,use_errno=True)
assert libc.ptrace(0,0,0,0) == -1 and ctypes.get_errno() == errno.EPERM
import torch
assert torch.ones(2).sum().item() == 2
print('isolation boundary passed')
'''
        environment = {"PATH": os.environ["PATH"], "PYTHONPATH": "/task/runtime",
                       "HOME": str(work), "TMPDIR": str(work), "OMP_NUM_THREADS": "1"}
        libc = ctypes.CDLL(None)
        for filesystem_identity in (0,10001):
            child = subprocess.Popen([sys.executable, "-c", code], env=environment,
                                     stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,text=True)
            old_gid=libc.setfsgid(filesystem_identity)
            old_uid=libc.setfsuid(filesystem_identity)
            try:
                stdout,stderr=child.communicate('probe\n',timeout=30)
            finally:
                libc.setfsuid(old_uid);libc.setfsgid(old_gid)
                if child.poll() is None:child.kill();child.wait()
            self.assertEqual(child.returncode,0,stdout+stderr)
            self.assertEqual(os.geteuid(),0)
        self.assertTrue((work / "allowed").is_file())


if __name__ == "__main__":
    unittest.main()
