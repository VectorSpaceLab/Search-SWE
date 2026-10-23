"""Real kernel/process boundary regressions; run only in a disposable container."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'runtime'))
from evaluate import evaluate, freeze_submission, run_query
from isolation import protect, members
from model import Meter


class FakeResources:
    def check(self, disk=False):
        pass


class FakeBackend:
    """Synthetic inference delays/charges isolate broker behavior from model quality."""
    pending = None
    def request(self, request, spent, candidates, timeout):
        import time
        time.sleep(.02)
        meter = Meter()
        meter.spent = spent
        try:
            if request.get('type') != 'generate':
                raise ValueError('Bad request')
            r = meter.reserve(200, 1)
            meter.settle(r, 1)
            return {'reply': {'type': 'generation', 'text': 'Yes', 'spent_tokens': meter.spent},
                    'meter_spent': meter.spent, 'calls': meter.calls}
        except ValueError as error:
            return {'error': str(error), 'meter_spent': meter.spent, 'calls': meter.calls}


@unittest.skipUnless(os.environ.get('SEARCH_SWE_ISOLATION_TEST') == '1',
                     'Requires disposable Docker container, never host execution')
class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        protect()
        Path('/tests/private-token').write_text('not-readable-by-submission')
        Path('/tests/private-token').chmod(0o600)
        cls.output = Path('/logs/verifier/kernel-tests')
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.output.chmod(0o700)
        cls.root = Path('/app/kernel-fixtures')
        cls.root.mkdir(exist_ok=True)
        cls.root.chmod(0o755)
        cls.counter = 0

    def run_code(self, body):
        type(self).counter += 1
        p = self.root/str(self.counter)
        p.mkdir()
        (p/'deployment.json').write_text('{}')
        (p/'strategy.py').write_text('import json,sys,os,time\nq=json.loads(sys.stdin.readline())\n'+body)
        (p/'run.sh').write_text('#!/bin/sh\nexec /opt/conda/bin/python "$(dirname "$0")/strategy.py"\n')
        (p/'run.sh').chmod(0o755)
        freeze_submission(p)
        q = {'query_id': str(self.counter), 'query': 'test',
             'candidates': [{'doc_id': 'a', 'text': 'passage', 'rank': 1, 'bm25_score': 1.0}]}
        result = run_query(q, p, FakeBackend(), self.output, FakeResources())
        self.assertFalse(members(), 'No live or orphan strategy child may remain')
        return result

    def test_real_kernel_permissions_and_normal_execution(self):
        result = self.run_code('''
import ctypes,errno,fcntl,socket,glob
denied=[]
def blocked(name,fn):
 try:fn()
 except OSError as e:
  assert e.errno in (errno.EPERM,errno.EACCES), (name,e)
  denied.append(name)
 else:raise AssertionError('Bypass: '+name)
blocked('hidden',lambda:open('/tests/private-token').read())
blocked('reward',lambda:open('/logs/verifier/reward.txt','w'))
blocked('trusted-code',lambda:open('/tests/runtime/model.py','w'))
blocked('outside-write',lambda:open('/tmp/strategy-escape','w'))
blocked('network',lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM))
devices=glob.glob('/dev/nvidia[0-9]*')
if os.environ.get('REQUIRE_GPU_TEST')=='1':assert devices
for device in devices:blocked('gpu-'+device,lambda d=device:os.open(d,os.O_RDWR))
with open('/dev/null','rb') as f:
 blocked('gpu-ioctl',lambda:fcntl.ioctl(f.fileno(),0x4600,0))
libc=ctypes.CDLL(None,use_errno=True)
assert libc.unshare(0x10000000)==-1 and ctypes.get_errno()==errno.EPERM
open('/work/allowed','w').write('permitted')
print(json.dumps({'denied':denied}),file=sys.stderr,flush=True)
print(json.dumps({'type':'result','ids':['a']}),flush=True)
''')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['ids'], ['a'])
        details = json.loads((self.output/(result['query_id']+'.stderr')).read_text())
        if os.environ.get('REQUIRE_GPU_TEST') == '1':
            self.assertTrue(any(s.startswith('gpu-/dev/nvidia') for s in details['denied']), details)

    def test_duplicate_and_out_of_pool_ids(self):
        for ids in (['a', 'a'], ['not-a-candidate'], [1]):
            with self.subTest(ids=ids):
                r = self.run_code('print('+repr(json.dumps({'type': 'result', 'ids': ids}))+',flush=True)\n')
                self.assertEqual(r['status'], 'failed', r)

    def test_root_artifact_symlink_rejected_before_privileged_traversal(self):
        target = Path('/app/private-target')
        target.mkdir(mode=0o700)
        link = Path('/app/submission-link')
        link.symlink_to(target, target_is_directory=True)
        before = target.stat().st_mode
        with self.assertRaisesRegex(ValueError, 'linked submission'):
            evaluate(link, '/not-used', '/not-used', self.output/'link-check')
        self.assertEqual(target.stat().st_mode, before)

    def test_timeout_and_orphan_cleanup(self):
        r = self.run_code('''
if os.fork()==0:
 os.setsid()
 while True:pass
time.sleep(2)
''')
        self.assertEqual(r['status'], 'failed', r)
        self.assertLess(r['local_seconds'], 1.2)

    def test_budget_shared_across_queued_child_requests(self):
        r = self.run_code('''
line=json.dumps({'type':'generate','messages':[{'role':'user','content':'test'}],'max_new_tokens':1})+'\\n'
children=[]
for _ in range(2):
 pid=os.fork()
 if pid==0:
  for i in range(6):os.write(1,line.encode())
  os._exit(0)
 children.append(pid)
for _ in range(12):sys.stdin.readline()
print(json.dumps({'type':'result','ids':['a']}),flush=True)
''')
        self.assertEqual(r['status'], 'failed', r)
        self.assertEqual(r['spent_tokens'], 2040)
        self.assertEqual(len(r['calls']), 10)
        self.assertIn('budget exceeded', r['error'])

    def test_inference_wait_and_descendant_freezing(self):
        r = self.run_code('''
pid=os.fork()
if pid==0:
 while True:pass
for _ in range(3):
 print(json.dumps({'type':'generate','messages':[{'role':'user','content':'test'}],'max_new_tokens':1}),flush=True)
 sys.stdin.readline()
print(json.dumps({'type':'result','ids':['a']}),flush=True)
''')
        self.assertEqual(r['status'], 'ok', r)
        self.assertGreater(r['inference_seconds'], .05)
        self.assertLess(r['local_seconds'], 1)

    def test_missing_output_nonzero_exit_and_stderr_flood(self):
        for code in ('os._exit(7)\n', 'print("not json",flush=True)\n',
                     'os.write(2,b"x"*(2<<20))\n'):
            with self.subTest(code=code):
                r = self.run_code(code)
                self.assertEqual(r['status'], 'failed', r)


if __name__ == '__main__':
    unittest.main()
