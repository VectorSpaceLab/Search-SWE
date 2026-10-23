"""Public development check; final limits are enforced by the private supervisor."""
import argparse
import json
from pathlib import Path
import select
import subprocess
import time
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--command', default='/app/run.sh')
    p.add_argument('--queries', type=int, default=100)
    p.add_argument('--index', default='/app/index')
    p.add_argument('--work-dir', default='/app/selfcheck-tmp')
    args = p.parse_args()
    if not 1 <= args.queries <= 5000:
        p.error('--queries must be between 1 and 5000')
    public = Path('/task/data/public')
    queries = np.fromfile(public / 'dev/vectors.f32', dtype='<f4').reshape(-1,32,128)
    truth = np.fromfile(public / 'dev/truth.i32', dtype='<i4').reshape(-1,100)
    ids = json.loads((public / 'corpus/ids.json').read_text())
    rows = {value:i for i,value in enumerate(ids)}
    Path(args.work_dir).mkdir(parents=True,exist_ok=True)
    proc = subprocess.Popen([args.command], stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def request(obj, timeout=120):
        proc.stdin.write(json.dumps(obj,separators=(',',':'))+'\n');proc.stdin.flush()
        if not select.select([proc.stdout],[],[],timeout)[0]:
            raise TimeoutError('No response before timeout')
        line = proc.stdout.readline(1<<20)
        if not line or not line.endswith('\n'):
            raise ValueError('Missing or oversized response')
        return json.loads(line)
    try:
        t=time.monotonic()
        assert request({'op':'load','corpus':str(public/'corpus'),'index':args.index,'work_dir':args.work_dir}) == {'ok':True}
        load_seconds=time.monotonic()-t
        for i in range(5): request({'op':'query','query_id':i,'vectors':queries[i].tolist()},30)
        total=0
        t=time.monotonic()
        responses=[request({'op':'query','query_id':i,'vectors':queries[i].tolist()}) for i in range(args.queries)]
        seconds=time.monotonic()-t
        for i,res in enumerate(responses):
            if not isinstance(res,dict) or type(res.get('query_id')) is not int or res['query_id']!=i or not isinstance(res.get('results'),list) or len(res['results'])>100:
                continue
            valid=set();previous=None;ok=True
            for item in res['results']:
                if not isinstance(item,dict) or not isinstance(item.get('doc_id'),str) or type(item.get('score')) not in (int,float) or not np.isfinite(item['score']):
                    ok=False;break
                row=rows.get(item['doc_id'])
                if row is None: continue
                key=(-item['score'],row)
                if previous is not None and key<previous: ok=False;break
                previous=key;valid.add(row)
            if ok: total+=len(valid.intersection(truth[i]))/100
        print(json.dumps({'queries':args.queries,'recall_at_100':total/args.queries,
                          'query_seconds':seconds,'load_seconds':load_seconds,'queries_per_second':args.queries/seconds},indent=2))
    finally:
        proc.kill();proc.wait()


if __name__=='__main__': main()
