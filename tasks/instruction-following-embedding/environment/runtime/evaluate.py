"""Trusted complete-candidate evaluation; no submitted code runs in this process."""
import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import tempfile

import numpy as np
import pynvml
from isolation import UID,isolate,cleanup
from metrics import evaluate_pairs,reward,rank_vectors
from models import validate

SUB=Path('/app/submission')
WORK=Path('/app/worker')
PREPARE_SECONDS=3600.
QUERY_SECONDS=1.


def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def read(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


class ResourceViolation(RuntimeError):pass


class Worker:
    def __init__(self,role,output,resources):
        cleanup()
        self.work=Path(tempfile.mkdtemp(prefix='encoder-',dir='/app'))
        self.work.chmod(0o700);os.chown(self.work,UID,UID)
        self.log=open(output/f'{role}-worker.stderr','ab')
        env={k:os.environ[k] for k in ['PATH','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','NVIDIA_DRIVER_CAPABILITIES'] if k in os.environ}
        env.update(HOME=str(self.work),TMPDIR=str(self.work),ENCODER_WORK_DIR=str(self.work),XDG_CACHE_HOME=str(self.work/'cache'),HF_HOME=str(self.work/'hf'),
                   OMP_NUM_THREADS='16',OPENBLAS_NUM_THREADS='16',MKL_NUM_THREADS='16',TOKENIZERS_PARALLELISM='false',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        self.p=subprocess.Popen(['/opt/conda/bin/python','/task/runtime/worker.py',role],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,env=env,bufsize=0)
        os.set_blocking(self.p.stdin.fileno(),False)
        self.selector=selectors.DefaultSelector();self.selector.register(self.p.stdout,selectors.EVENT_READ)
        self.buffer=b'';self.resources=resources
    def receive(self,deadline):
        while b'\n' not in self.buffer:
            self.resources.check()
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Encoding deadline exceeded')
            if self.selector.select(min(.05,remaining)):
                b=os.read(self.p.stdout.fileno(),65536)
                if not b:raise RuntimeError('Worker exited before returning a response')
                self.buffer+=b
                if len(self.buffer)>8<<20:raise ValueError('Oversized worker response')
        line,self.buffer=self.buffer.split(b'\n',1)
        r=json.loads(line)
        if r.get('model_violation'):raise ResourceViolation(r.get('error','Model execution constraint violation'))
        if 'error' in r:raise ValueError(r['error'])
        return r
    def call(self,message,deadline):
        payload=(json.dumps(message,separators=(',',':'))+'\n').encode()
        view=memoryview(payload)
        while view:
            self.resources.check()
            if time.monotonic()>=deadline:raise TimeoutError('Worker input deadline exceeded')
            try:
                n=os.write(self.p.stdin.fileno(),view);view=view[n:]
            except BlockingIOError:time.sleep(.005)
        return self.receive(deadline)['vectors']
    def close(self):
        cleanup()
        if self.p.poll() is None:self.p.kill()
        self.p.wait(timeout=10);self.selector.close();self.log.close()
        self.p.stdin.close();self.p.stdout.close()


class Resources:
    def __init__(self):
        pynvml.nvmlInit()
        if pynvml.nvmlDeviceGetCount()!=1:raise RuntimeError('Exactly one mapped GPU required')
        self.gpu=pynvml.nvmlDeviceGetHandleByIndex(0)
        self.peak_gpu=0;self.peak_disk=0;self.last_disk=0
        self.fixed=sum(p.stat().st_size for root in [Path('/task/models'),Path('/task/corpus')] for p in root.rglob('*') if p.is_file())
    def check(self):
        used=pynvml.nvmlDeviceGetMemoryInfo(self.gpu).used;self.peak_gpu=max(self.peak_gpu,used)
        if used>40<<30:raise ResourceViolation('40 GiB physical GPU budget exceeded')
        if time.monotonic()-self.last_disk>=1:
            self.last_disk=time.monotonic()
            total=self.fixed+sum(p.stat().st_size for p in Path('/app').rglob('*') if p.is_file() and not p.is_symlink())
            self.peak_disk=max(self.peak_disk,total)
            if total>32<<30:raise ResourceViolation('32 GiB task storage exceeded')
    def report(self):
        return {'peak_gpu_bytes':self.peak_gpu,'peak_task_storage_bytes':self.peak_disk,
                'gpu':pynvml.nvmlDeviceGetName(self.gpu),'gpu_uuid':pynvml.nvmlDeviceGetUUID(self.gpu)}


def freeze_submission():
    validate(SUB)
    for p in [SUB,*SUB.rglob('*')]:
        os.chown(p,0,0);p.chmod(0o555 if p.is_dir() else 0o444)


def evaluate(groups,output,anchors=None):
    started=time.monotonic();deadline=started+PREPARE_SECONDS
    output.mkdir(parents=True,exist_ok=True)
    freeze_submission();resources=Resources()
    corpus=[];keys=[]
    for subset in ['robust04','core17','news21']:
        for r in read(f'/task/corpus/{subset}.jsonl'):
            keys.append(subset+'/'+str(r['_id']));corpus.append((r['title']+' '+r['text']).strip())
    index={k:i for i,k in enumerate(keys)}
    if len(index)!=len(keys):raise ValueError('Duplicate corpus ID')
    cache=Path('/app/documents.npy')
    docs=np.lib.format.open_memmap(cache,mode='w+',dtype='float32',shape=(len(keys),1024))
    w=Worker('document',output,resources)
    try:
        if not w.receive(deadline).get('ready'):raise ValueError('Worker initialization')
        for start in range(0,len(corpus),32):
            texts=corpus[start:start+32]
            v=np.asarray(w.call({'texts':texts},deadline),dtype=np.float32)
            if v.shape!=(len(texts),1024) or not np.isfinite(v).all():raise ValueError('Invalid document vectors')
            norms=np.linalg.norm(v,axis=1)
            if np.any(norms==0):raise ValueError('Zero document vector')
            docs[start:start+len(texts)]=v/norms[:,None]
        docs.flush()
        # Check independence from batch order/content on a fixed, public sample.
        selected=[0,len(corpus)//2,len(corpus)-1]
        for i in selected:
            v=np.asarray(w.call({'texts':[corpus[i]]},deadline),dtype=np.float32)
            v/=np.linalg.norm(v,axis=1,keepdims=True)
            # bf16 GEMMs differ slightly between singleton and batched shapes.
            if float(v[0]@docs[i])<.999:raise ValueError('Document representations depend on batching beyond bf16 tolerance')
    finally:w.close()
    w=Worker('query',output,resources)
    try:
        if not w.receive(deadline).get('ready'):raise ValueError('Query initialization')
        for _ in range(3):w.call({'query':'Find information about road safety.','instruction':'Include reports comparing vehicles.'},deadline)
        prepare=time.monotonic()-started
        rankings={};timings=[];failures=[]
        for g in groups:
            result=[]
            for version in ['og','changed']:
                begin=time.monotonic()
                try:
                    rows=[index[g['subset']+'/'+d] for d in g['candidates']]
                    documents=np.asarray(docs[rows])
                    vector=w.call({'query':g['query'],'instruction':g['instruction_'+version]},begin+QUERY_SECONDS)
                    ranking=rank_vectors(vector,documents,g['candidates'])
                    elapsed=time.monotonic()-begin
                    if elapsed>QUERY_SECONDS:raise TimeoutError('Query encoding plus scoring exceeded 1 second')
                    result.append(ranking)
                except ResourceViolation:raise
                except Exception as exc:
                    elapsed=time.monotonic()-begin
                    failures.append({'key':g['key'],'version':version,'error':str(exc)})
                    result.append(None)
                    # Timed-out/broken workers are killed and reloaded within the
                    # same total verifier budget; no retry of this query group.
                    if isinstance(exc,(TimeoutError,BrokenPipeError,RuntimeError)):
                        w.close();w=Worker('query',output,resources)
                        if not w.receive(time.monotonic()+60).get('ready'):raise RuntimeError('Worker recovery failed')
                timings.append({'key':g['key'],'version':version,'seconds':elapsed})
            if all(r is not None for r in result):rankings[g['key']]=result
        report=evaluate_pairs(groups,rankings)
        report.update(valid=True,prepare_seconds=prepare,total_seconds=time.monotonic()-started,timings=timings,failures=failures,resources=resources.report())
        if anchors is not None:
            score,gates=reward(report,anchors);report.update(reward=score,score=100*score,gates=gates)
        dump(output/'report.json',report)
        return report
    finally:
        w.close();cache.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--groups',default='/task/public/dev-groups.json');p.add_argument('--output',default='/app/evaluation');p.add_argument('--anchors');args=p.parse_args()
    try:
        report=evaluate(json.loads(Path(args.groups).read_text()),Path(args.output),json.loads(Path(args.anchors).read_text()) if args.anchors else None)
        print(json.dumps({k:report[k] for k in ['P','subsets','prepare_seconds','resources']}))
    finally:cleanup()

if __name__=='__main__':main()
