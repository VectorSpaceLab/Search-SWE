"""Public smoke/evaluation client; final resource enforcement is verifier-owned."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import select
import selectors
import signal
import subprocess
import time
from oracle_client import call

p=argparse.ArgumentParser()
p.add_argument('--command',nargs=argparse.REMAINDER,required=True)
p.add_argument('--limit',type=int,default=500)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if not a.command:p.error('--command must be followed by the program and its arguments')
if not 1 <= a.limit <= 500:p.error('--limit must be in 1..500')
config=json.loads(Path('/task/public/config.json').read_text())
queries=[json.loads(x) for x in Path('/task/public/dev-queries.jsonl').read_text().splitlines()][:a.limit]
labels={}
with Path('/task/public/dev-qrels.tsv').open() as f:
    for row in csv.DictReader(f,delimiter='\t'):
        labels.setdefault(row['query-id'],{})[row['corpus-id']]=int(row['score'])
proc=subprocess.Popen(a.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,start_new_session=True)
sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ)
os.set_blocking(proc.stdout.fileno(),False)
os.set_blocking(proc.stdin.fileno(),False)
buffer=bytearray()


def receive(deadline):
    while b'\n' not in buffer:
        if not sel.select(max(0,deadline-time.monotonic())):raise TimeoutError('Submission timeout')
        chunk=os.read(proc.stdout.fileno(),65536)
        if not chunk:raise RuntimeError('Submission exited')
        buffer.extend(chunk)
        if len(buffer)>1<<20:raise RuntimeError('Protocol line exceeds 1 MiB')
    if time.monotonic()>deadline:raise TimeoutError('Submission timeout')
    line,_,tail=buffer.partition(b'\n');buffer[:]=tail
    return json.loads(line)


def send(value,deadline):
    data=memoryview((json.dumps(value)+'\n').encode())
    while data:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Submission timeout writing input')
        if not select.select([], [proc.stdin], [], remaining)[1]:
            raise TimeoutError('Submission timeout writing input')
        try:data=data[os.write(proc.stdin.fileno(),data):]
        except BlockingIOError:pass


results=[]
try:
    if receive(time.monotonic()+3600)!={'op':'ready'}:raise RuntimeError('Expected ready')
    for query in queries:
        begin=call('/begin',{'query_id':query['query_id']})
        t0=time.monotonic();deadline=t0+2
        token=begin['token'];used=0
        send({'op':'query','token':token,'text':query['text'],'vector':query['vector']},deadline)
        while True:
            reply=receive(deadline)
            if reply.get('op')=='score':
                response=call('/score',reply);used=response['used'];send(response,deadline)
            else:
                if set(reply)!={'op','token','doc_ids'} or reply.get('op')!='result' or reply.get('token')!=token:raise RuntimeError('Invalid result')
                ids=reply['doc_ids']
                if (not isinstance(ids,list) or len(ids)>10 or
                    any(not isinstance(doc,str) or not re.fullmatch(r'doc(?:0|[1-9][0-9]*)',doc) or len(doc)>3+len(str(config['documents']-1)) or int(doc[3:])>=config['documents'] for doc in ids) or
                    len(set(ids))!=len(ids)):raise RuntimeError('Invalid ranking')
                qrels=labels[query['query_id']]
                dcg=sum((2**qrels.get(doc,0)-1)/math.log2(i+2) for i,doc in enumerate(ids))
                ideal=sum((2**rel-1)/math.log2(i+2) for i,rel in enumerate(sorted(qrels.values(),reverse=True)[:10]))
                results.append({'query_id':query['query_id'],'ndcg10':dcg/ideal if ideal else 0,
                                'calls':used,'seconds':time.monotonic()-t0,'doc_ids':ids})
                break
finally:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    proc.wait();sel.close()
    a.output.write_text(json.dumps({'completed':len(results),'requested':len(queries),'queries':results},indent=2)+'\n')
if len(results)==len(queries):print('development nDCG@10',sum(r['ndcg10'] for r in results)/len(queries))
