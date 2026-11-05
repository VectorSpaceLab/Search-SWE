"""Exercise the audit UID and filesystem policy without calling a model."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


@unittest.skipUnless(os.environ.get('SEARCH_SWE_RUN_ISOLATION_TESTS') == '1'
                     and Path('/.dockerenv').exists() and os.getuid() == 0,
                     'requires an explicitly opted-in disposable verifier container')
class AuditIsolationTests(unittest.TestCase):
    def test_audit_can_read_evidence_but_not_change_it_or_access_grading(self):
        for path in ('/app/submission', '/logs/verifier', '/audit/config', '/audit/output', '/home/audit/tmp'):
            Path(path).mkdir(parents=True, exist_ok=True)
        Path('/app/submission/source.py').write_text('untrusted fixture')
        Path('/audit/trajectory.json').write_text('protected evidence')
        Path('/logs/verifier/evaluation.json').write_text('private score')
        Path('/tests/private-audit-sentinel').write_text('private labels')
        for path in ('/app', '/app/submission'):
            shutil.chown(path, user='root', group='submission')
            Path(path).chmod(0o550)
        shutil.chown('/app/submission/source.py', user='root', group='submission')
        Path('/app/submission/source.py').chmod(0o440)
        shutil.chown('/audit', user='root', group='audit')
        Path('/audit').chmod(0o750)
        shutil.chown('/audit/trajectory.json', user='root', group='audit')
        Path('/audit/trajectory.json').chmod(0o440)
        for path in ('/audit/output', '/home/audit/tmp'):
            shutil.chown(path, user='audit', group='audit')
            Path(path).chmod(0o700)
        code = '''from pathlib import Path
import os,sys
sys.path.insert(0,'/opt/audit')
from landlock_audit import restrict_audit
restrict_audit()
assert os.getuid()==10002
assert Path('/app/submission/source.py').read_text()=='untrusted fixture'
assert Path('/audit/trajectory.json').read_text()=='protected evidence'
for path in ['/app/submission/source.py','/audit/trajectory.json','/logs/verifier/evaluation.json','/tests/private-audit-sentinel']:
 try: Path(path).write_text('tampered')
 except PermissionError: pass
 else: raise AssertionError('Writable: '+path)
for path in ['/logs/verifier/evaluation.json','/tests/private-audit-sentinel','/proc/self/environ']:
 try: Path(path).read_bytes()
 except PermissionError: pass
 else: raise AssertionError('Readable: '+path)
Path('/audit/output/fixture.json').write_text('{}')
Path('/home/audit/tmp/fixture').write_text('allowed scratch')
'''
        result = subprocess.run(['/usr/sbin/runuser', '-u', 'audit', '--',
                                 sys.executable, '-B', '-c', code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path('/logs/verifier/evaluation.json').read_text(), 'private score')


if __name__ == '__main__':
    unittest.main()
