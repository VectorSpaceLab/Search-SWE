"""Run only inside the disposable verifier image, as root."""
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
import numpy as np
from metrics import ndcg10, reward
from oracle import Oracle, QueryFailure
from runtime import Worker, Violation, members


@unittest.skipUnless(os.getuid()==0 and Path('/tests').is_dir(), 'container-only runtime checks')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp')
        self.base=Path(self.tmp.name);self.base.chmod(0o755)
        self.work=self.base/'work';self.work.mkdir(mode=0o700);os.chown(self.work,10001,10001)
        self.worker=None

    def tearDown(self):
        if self.worker:self.worker.close()
        self.assertEqual(list(members()),[])
        self.tmp.cleanup()

    def launch(self, source, fixed=0):
        script=self.work/'fixture.py';script.write_text(source);script.chmod(0o644)
        self.worker=Worker(['/opt/conda/bin/python','-u',str(script)],str(self.work),
                           self.base/'stderr',sorted(os.sched_getaffinity(0))[:2],fixed)
        return self.worker

    def test_valid_adaptive_query(self):
        w=self.launch('''import json,sys
print(json.dumps({'op':'ready'}),flush=True)
q=json.loads(sys.stdin.readline())
for ids in [['doc0'],['doc1','doc2']]:
 print(json.dumps({'op':'score','token':q['token'],'doc_ids':ids}),flush=True)
 response=json.loads(sys.stdin.readline())
print(json.dumps({'op':'result','token':q['token'],'doc_ids':['doc2','doc1']}),flush=True)
sys.stdin.readline()
''')
        self.assertEqual(w.receive(time.monotonic()+10),{'op':'ready'})
        w.suspend();deadline=time.monotonic()+2
        oracle=Oracle(np.array([[1,0],[.8,.6],[0,1]],dtype='f4'))
        oracle.begin([0,1],'a',deadline)
        w.resume();w.send({'op':'query','token':'a','text':'example','vector':[0,1]},deadline)
        for _ in range(2): w.send(oracle.score(w.receive(deadline)),deadline)
        result=w.receive(deadline);w.suspend()
        self.assertEqual(oracle.used,3)
        self.assertEqual(result['doc_ids'],['doc2','doc1'])
        self.assertEqual(ndcg10(result['doc_ids'],{'doc2':1}),1)
        self.assertEqual(reward(1,.4,.8),1)

    def test_hidden_reward_network_and_affinity_isolation(self):
        private=self.base/'private';private.mkdir(mode=0o700)
        (private/'sentinel').write_text('not visible')
        reward_path=private/'reward.txt';reward_path.write_text('0')
        source='''import json,socket,os,sys
out={}
tests={'hidden':lambda:open(HIDDEN).read(),'reward':lambda:open(REWARD,'w'),
       'network':lambda:socket.socket(socket.AF_INET),
       'affinity':lambda:os.sched_setaffinity(0,range(256)),
       'ptrace':lambda:open('/proc/1/mem','rb')}
for name,fn in tests.items():
 try: fn();out[name]='allowed'
 except (PermissionError,OSError):out[name]='denied'
out['unix_ipc']=bool(socket.socketpair())
print(json.dumps(out),flush=True)
sys.stdin.readline()
'''.replace('HIDDEN',repr(str(private/'sentinel'))).replace('REWARD',repr(str(reward_path)))
        w=self.launch(source);result=w.receive(time.monotonic()+10)
        self.assertEqual(result,{'hidden':'denied','reward':'denied','network':'denied','affinity':'denied','ptrace':'denied','unix_ipc':True})
        self.assertEqual(reward_path.read_text(),'0')

    def test_timeout_and_descendant_cleanup(self):
        w=self.launch('''import os,time,json
if os.fork()==0:
 os.setsid()
 if os.fork()!=0:os._exit(0)
 time.sleep(100)
else:
 print(json.dumps({'op':'ready'}),flush=True)
 time.sleep(100)
''')
        self.assertEqual(w.receive(time.monotonic()+10),{'op':'ready'})
        with self.assertRaisesRegex(Violation,'timeout'):w.receive(time.monotonic()+.05)

    def test_output_flood(self):
        w=self.launch("import sys,time;sys.stdout.write('x'*2000000);sys.stdout.flush();time.sleep(10)")
        with self.assertRaisesRegex(Violation,'1 MiB'):w.receive(time.monotonic()+10)

    def test_invalid_json(self):
        w=self.launch("import time;print('garbage',flush=True);time.sleep(10)")
        with self.assertRaisesRegex(Violation,'invalid JSONL'):w.receive(time.monotonic()+10)

    def test_nested_json_is_a_submission_failure(self):
        depth=20000  # Also exceed Python 3.12's separate C JSON decoder guard.
        w=self.launch(f"import time;print('['*{depth}+'0'+']'*{depth},flush=True);time.sleep(10)")
        with self.assertRaisesRegex(Violation,'invalid JSONL'):w.receive(time.monotonic()+10)

    def test_invalid_executable_is_a_submission_failure(self):
        script=self.work/'invalid.sh';script.write_text('no executable header');script.chmod(0o755)
        with self.assertRaisesRegex(Violation,'Cannot launch submission'):
            Worker([str(script)],str(self.work),self.base/'stderr',sorted(os.sched_getaffinity(0))[:2])

    def test_aggregate_storage_includes_fixed_inputs(self):
        w=self.launch("import time; f=open('large','wb');f.truncate(64<<30);f.close();print('{}',flush=True);time.sleep(10)",fixed=1<<30)
        w.receive(time.monotonic()+10)
        with self.assertRaisesRegex(Violation,'storage'):w.sample(force_disk=True)

    def test_worker_stopped_between_queries(self):
        w=self.launch('''import json,sys,time,os
if os.fork()==0:
 while True:
  with open('ticks','a') as f:f.write('x')
  time.sleep(.001)
print(json.dumps({'op':'ready'}),flush=True)
sys.stdin.readline()
''')
        w.receive(time.monotonic()+10);time.sleep(.02);w.suspend()
        size=(self.work/'ticks').stat().st_size
        time.sleep(.05)
        self.assertEqual((self.work/'ticks').stat().st_size,size)


if __name__=='__main__':unittest.main()
