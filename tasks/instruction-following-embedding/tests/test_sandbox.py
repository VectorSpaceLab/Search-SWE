"""Disposable-container kernel boundary regressions; no host-side /app writes."""
import json
import errno
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,'/task/runtime')

@unittest.skipUnless(os.environ.get('SEARCH_SWE_SANDBOX_TEST')=='1','Run only in the disposable verifier container')
class SandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from isolation import UID
        for path in ['/app/submission','/app/worker','/task/models','/task/corpus','/logs/verifier']:
            Path(path).mkdir(parents=True,exist_ok=True)
        os.chown('/app/worker',UID,UID);os.chmod('/app/worker',0o700)
        Path('/tests/hidden-sentinel').write_text('hidden');os.chmod('/tests/hidden-sentinel',0o600)
        Path('/task/corpus/sentinel').write_text('document')
        Path('/app/submission/sentinel').write_text('model')
        os.chmod('/logs/verifier',0o700)
    def run_code(self,code):
        from isolation import isolate
        p=subprocess.run(['/opt/conda/bin/python','-c',code],text=True,capture_output=True,
                         env={'PATH':'/opt/conda/bin:/usr/bin:/bin'},timeout=10,
                         preexec_fn=lambda:isolate('/app/worker'))
        self.assertEqual(p.returncode,0,p.stderr)
        return p.stdout.strip()
    def test_hidden_grader_reward_and_corpus_denied(self):
        for path,mode in [('/tests/hidden-sentinel','r'),('/task/corpus/sentinel','r'),('/logs/verifier/reward.txt','w'),('/app/submission/sentinel','w'),('/task/runtime/worker.py','w')]:
            code=f"import errno\ntry:\n open({path!r},{mode!r});print('accessible')\nexcept OSError as e:\n assert e.errno in (errno.EACCES,errno.EPERM,errno.EROFS)\n print('denied')"
            self.assertEqual(self.run_code(code),'denied')
    def test_scratch_write_and_readonly_model_allowed(self):
        code="from pathlib import Path\nPath('/app/worker/output').write_text('ok')\nprint(Path('/app/submission/sentinel').read_text())"
        self.assertEqual(self.run_code(code),'model')
    def test_internet_socket_denied(self):
        self.assertEqual(self.run_code("import socket\ntry:\n socket.socket(socket.AF_INET);print('accessible')\nexcept PermissionError:print('denied')"),'denied')
    def test_descendant_keeps_boundary(self):
        code="import subprocess\np=subprocess.run(['/opt/conda/bin/python','-c',\"open('/tests/hidden-sentinel').read()\"],capture_output=True)\nprint(p.returncode != 0)"
        self.assertEqual(self.run_code(code),'True')
    def test_privilege_escalation_denied(self):
        self.assertEqual(self.run_code("import os\ntry:\n os.setuid(0);print('root')\nexcept PermissionError:print('denied')"),'denied')

if __name__=='__main__':unittest.main()
