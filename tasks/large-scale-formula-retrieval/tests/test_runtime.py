"""Container-only tests: run in a disposable verifier, never against host UID 10001."""
import json
import os
from pathlib import Path
import sys
import unittest

import psutil
import runtime
from runtime import Worker, Violation


FIXTURE = '''import ctypes,json,os,socket,sys,time
for line in sys.stdin:
 r=json.loads(line); op=r['op']
 if op=='ipc_transfer':
  c=ctypes.CDLL(None,use_errno=True)
  objects=[]
  for kind in ['shm','msg','sem']:
   if kind=='shm': ident=c.shmget(0,4096,0o1600)
   elif kind=='msg': ident=c.msgget(0,0o1600)
   else: ident=c.semget(0,1,0o1600)
   assert ident>=0,ctypes.get_errno()
   buf=ctypes.create_string_buffer(512)
   def control(command):
    if kind=='sem': return c.semctl(ident,0,command,ctypes.byref(buf))
    return getattr(c,kind+'ctl')(ident,command,ctypes.byref(buf))
   assert control(2)==0,ctypes.get_errno()
   perm=(ctypes.c_uint*5).from_buffer(buf)
   assert perm[1]==perm[3]==os.getuid()
   perm[1]=perm[2]=65534
   assert control(1)==0,ctypes.get_errno()
   objects.append([kind,ident])
  print(json.dumps({'objects':objects}),flush=True);continue
 if op=='save_index':
  open('saved-index','w').write('legitimate index')
  print(json.dumps({'ok':True}),flush=True);continue
 if op=='load_index':
  print(json.dumps({'index':open('saved-index').read()}),flush=True);continue
 if op in ['ipc_write','ipc_read']:
  c=ctypes.CDLL(None,use_errno=True)
  c.shmget.argtypes=[ctypes.c_int,ctypes.c_size_t,ctypes.c_int]
  c.shmget.restype=ctypes.c_int
  ident=c.shmget(1179864370,4096,0o1600 if op=='ipc_write' else 0o600)
  print(json.dumps({'exists':ident>=0}),flush=True);continue
 if op=='timeout': time.sleep(20)
 if op=='exit': sys.exit(3)
 if op=='malformed': print('oops',flush=True); continue
 if op=='deep': print('['*10000+'0'+']'*10000,flush=True); continue
 if op=='diagnostics': print('x'*(1<<20),file=sys.stderr,flush=True)
 if op=='oversize': print('x'*(2<<20),flush=True); continue
 if op=='memory': allocation=bytearray(128<<20)
 if op=='shared_memory':
  allocation=bytearray(128<<20)
  for _ in range(3):
   child=os.fork()
   if child==0: time.sleep(20); sys.exit(0)
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
        self.cpus = sorted(os.sched_getaffinity(0))[:16]
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

    def test_exit(self):
        self.worker.begin(5)
        with self.assertRaises(Violation):
            self.worker.request({'op': 'exit'})

    def test_actual_memory_excess(self):
        previous = runtime.MEMORY
        try:
            runtime.MEMORY = int(Path('/sys/fs/cgroup/memory.current').read_text()) + (64 << 20)
            self.worker.begin(5)
            with self.assertRaisesRegex(Violation, 'memory limit'):
                self.worker.request({'op': 'memory'})
                self.worker.finish()
        finally:
            runtime.MEMORY = previous

    def test_shared_pages_are_not_charged_per_process(self):
        previous = runtime.MEMORY
        try:
            runtime.MEMORY = int(Path('/sys/fs/cgroup/memory.current').read_text()) + (192 << 20)
            self.worker.begin(5)
            self.assertEqual(self.worker.request({'op': 'shared_memory'}), {'ok': True})
            result = self.worker.finish()
            # Four processes share one allocation: summed RSS exceeds the
            # temporary limit, while the real container charge remains below it.
            self.assertGreater(result['rss_bytes'], runtime.MEMORY)
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

    def test_deep_json_is_a_query_failure(self):
        self.worker.begin(5)
        self.assertIsNone(self.worker.request({'op': 'deep'}))
        self.assertEqual(self.worker.request({'op': 'query'}), {'ok': True})
        self.worker.finish()

    def test_diagnostics_cap_survives_restart(self):
        previous = runtime.MAX_DIAGNOSTICS, runtime._diagnostic_bytes
        runtime.MAX_DIAGNOSTICS, runtime._diagnostic_bytes = 1024, 0
        try:
            self.worker.begin(5)
            self.worker.request({'op': 'diagnostics'})
            self.worker.finish()
            self.assertEqual(Path('/logs/verifier/fixture.stderr').stat().st_size, 1024)
            self.worker.close()
            self.worker = Worker([sys.executable, '/fixture/worker.py'], '/work/test-worker',
                                 '/logs/verifier/second.stderr', self.cpus)
            self.worker.begin(5)
            self.worker.request({'op': 'diagnostics'})
            self.worker.finish()
            self.assertEqual(Path('/logs/verifier/second.stderr').stat().st_size, 0)
        finally:
            runtime.MAX_DIAGNOSTICS, runtime._diagnostic_bytes = previous

    def test_descendant_stopped_and_affinity_bounded(self):
        self.worker.begin(5)
        child = self.worker.request({'op': 'fork'})['child']
        self.worker.finish()
        self.assertEqual(psutil.Process(child).status(), psutil.STATUS_STOPPED)
        self.worker.begin(5, query=True)
        self.assertEqual(os.sched_getaffinity(child), set(self.cpus))
        self.worker.request({'op': 'query'})
        self.worker.finish()

    def test_build_kernel_ipc_does_not_survive_worker_close(self):
        self.worker.begin(5)
        self.assertEqual(self.worker.request({'op': 'ipc_write'}), {'exists': True})
        self.worker.finish()
        self.worker.close()
        self.worker = Worker([sys.executable, '/fixture/worker.py'], '/work/test-worker',
                             '/logs/verifier/ipc-reload.stderr', self.cpus)
        self.worker.begin(5)
        self.assertEqual(self.worker.request({'op': 'ipc_read'}), {'exists': False})
        self.worker.finish()

    def test_transferred_owners_are_removed_and_normal_index_reloads(self):
        self.worker.begin(5)
        objects = self.worker.request({'op': 'ipc_transfer'})['objects']
        self.assertEqual(self.worker.request({'op': 'save_index'}), {'ok': True})
        self.worker.finish()
        for kind, identifier in objects:
            rows = Path('/proc/sysvipc', kind).read_text().splitlines()
            name = {'shm': 'shmid', 'msg': 'msqid', 'sem': 'semid'}[kind]
            row = next(dict(zip(rows[0].split(), line.split())) for line in rows[1:]
                       if int(dict(zip(rows[0].split(), line.split()))[name]) == identifier)
            self.assertEqual((int(row['uid']), int(row['cuid'])), (65534, 10001))
        self.worker.close()
        self.assertEqual(runtime.worker_ipc(), [])
        for kind, identifier in objects:
            rows = Path('/proc/sysvipc', kind).read_text().splitlines()
            name = {'shm': 'shmid', 'msg': 'msqid', 'sem': 'semid'}[kind]
            column = rows[0].split().index(name)
            self.assertNotIn(identifier, {int(line.split()[column]) for line in rows[1:]})
        self.worker = Worker([sys.executable, '/fixture/worker.py'], '/work/test-worker',
                             '/logs/verifier/transferred-ipc-reload.stderr', self.cpus)
        self.worker.begin(5)
        self.assertEqual(self.worker.request({'op': 'load_index'}),
                         {'index': 'legitimate index'})
        self.worker.finish()


if __name__ == '__main__':
    unittest.main()
