"""Container-only tests: run in a disposable verifier, never against host UID 10001."""
import json
import os
from pathlib import Path
import sys
import unittest

import psutil
import runtime
from runtime import Worker, Violation


FIXTURE = '''import json,os,socket,sys,time
for line in sys.stdin:
 r=json.loads(line); op=r['op']
 if op=='timeout': time.sleep(20)
 if op=='stopreading': print('{"ok":true}',flush=True);time.sleep(20);continue
 if op=='exit': sys.exit(3)
 if op=='malformed': print('oops',flush=True); continue
 if op=='oversize': print('x'*(2<<20),flush=True); continue
 if op=='memory': allocation=bytearray(128<<20)
 if op=='disk':
  with open('large-file','wb') as f: f.truncate(128<<20)
 if op=='fork':
  child=os.fork()
  if child==0: os.setsid(); time.sleep(20); sys.exit(0)
  print(json.dumps({'child':child}),flush=True); continue
 if op=='checks':
  out={}
  a,b=socket.socketpair();a.send(b'ok');out['local_ipc']=b.recv(2).decode();a.close();b.close()
  for k,fn in [('hidden',lambda:open('/tests/private-sentinel').read()),('quota_image',lambda:open('/quota/private-sentinel').read()),('reward',lambda:open('/logs/verifier/reward.txt','w')),('network',lambda:socket.socket()),('affinity',lambda:os.sched_setaffinity(0,range(256)))]:
   try: fn();out[k]='allowed'
   except (PermissionError,OSError):out[k]='denied'
  out['cpus']=sorted(os.sched_getaffinity(0));out['uid']=os.getuid();out['key']=os.environ.get('OPENAI_API_KEY')
  out['capabilities']=int(next(s.split()[1] for s in open('/proc/self/status') if s.startswith('CapEff:')),16)
  print(json.dumps(out),flush=True);continue
 print(json.dumps({'ok':True}),flush=True)
'''


@unittest.skipUnless(Path('/.dockerenv').exists() and os.getuid() == 0, 'requires disposable root verifier container')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        Path('/tests/private-sentinel').write_text('hidden')
        Path('/quota').mkdir(mode=0o700, exist_ok=True)
        Path('/quota/private-sentinel').write_text('hidden backing storage')
        os.chmod('/tests', 0o700)
        Path('/logs/verifier').mkdir(parents=True, exist_ok=True)
        os.chmod('/logs/verifier', 0o700)
        Path('/logs/verifier/reward.txt').write_text('0')
        Path('/fixture').mkdir(exist_ok=True)
        Path('/fixture/worker.py').write_text(FIXTURE)
        self.cpus = sorted(os.sched_getaffinity(0))[:8]
        self.worker = Worker([sys.executable, '/fixture/worker.py'], '/work/test-worker', '/logs/verifier/fixture.stderr', self.cpus)

    def tearDown(self):
        self.worker.close()

    def test_protocol_and_actual_boundaries(self):
        self.worker.begin(10)
        self.assertEqual(self.worker.request({'op': 'build'}), {'ok': True})
        self.assertGreater(self.worker.finish()['rss_bytes'], 0)
        self.worker.begin(10, query=True)
        result = self.worker.request({'op': 'checks'})
        self.worker.finish()
        self.assertEqual(result, {'hidden': 'denied', 'quota_image': 'denied', 'reward': 'denied', 'network': 'denied',
                                 'affinity': 'allowed', 'local_ipc': 'ok', 'cpus': self.cpus, 'uid': 10001, 'key': None, 'capabilities': 0})

    def test_timeout(self):
        self.worker.begin(.2)
        with self.assertRaisesRegex(Violation, 'timeout'):
            self.worker.request({'op': 'timeout'})

    def test_timeout_while_request_pipe_is_full(self):
        self.worker.begin(5)
        self.assertEqual(self.worker.request({'op': 'stopreading'}), {'ok': True})
        self.worker.finish()
        self.worker.begin(.2)
        with self.assertRaisesRegex(Violation, 'timeout'):
            self.worker.request({'op': 'query', 'payload': 'x' * (2 << 20)})

    def test_exit(self):
        self.worker.begin(5)
        with self.assertRaises(Violation):
            self.worker.request({'op': 'exit'})

    def test_actual_memory_excess(self):
        previous = runtime.MEMORY
        try:
            runtime.MEMORY = 64 << 20
            self.worker.begin(5)
            with self.assertRaisesRegex(Violation, 'memory limit'):
                self.worker.request({'op': 'memory'})
                self.worker.finish()
        finally:
            runtime.MEMORY = previous

    def test_logical_storage_excess(self):
        previous = runtime.STORAGE
        try:
            runtime.STORAGE = 64 << 20
            self.worker.begin(5)
            with self.assertRaisesRegex(Violation, 'storage limit'):
                self.worker.request({'op': 'disk'})
                self.worker.finish()
        finally:
            runtime.STORAGE = previous
            Path('/work/test-worker/large-file').unlink(missing_ok=True)

    def test_oversize_protocol(self):
        self.worker.begin(5)
        with self.assertRaisesRegex(Violation, '1 MiB'):
            self.worker.request({'op': 'oversize'})

    def test_malformed_response_does_not_shift_next_query(self):
        self.worker.begin(5)
        self.assertIsNone(self.worker.request({'op': 'malformed'}))
        self.assertEqual(self.worker.request({'op': 'query'}), {'ok': True})
        self.worker.finish()

    def test_descendant_stopped_and_affinity_bounded(self):
        self.worker.begin(5)
        child = self.worker.request({'op': 'fork'})['child']
        self.worker.finish()
        self.assertEqual(psutil.Process(child).status(), psutil.STATUS_STOPPED)
        self.worker.begin(5, query=True)
        self.assertEqual(os.sched_getaffinity(child), set(self.cpus))
        self.worker.request({'op': 'query'})
        self.worker.finish()


if __name__ == '__main__':
    unittest.main()
