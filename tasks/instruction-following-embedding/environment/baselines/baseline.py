"""Reproduce the fixed-template, untrained E5 serving baseline on public groups."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel,AutoTokenizer
sys.path.insert(0,'/task/runtime')
from metrics import evaluate_pairs


def encode(model,tok,texts,batch):
    vectors=[]
    with torch.inference_mode():
        for start in range(0,len(texts),batch):
            b=tok(texts[start:start+batch],padding=True,truncation=True,max_length=512,return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                h=model(**b).last_hidden_state;mask=b['attention_mask'].unsqueeze(-1)
                v=F.normalize((h.float()*mask).sum(1)/mask.sum(1),dim=-1)
            vectors.append(v.cpu().numpy())
    return np.concatenate(vectors)


def format_input(query,instruction,template):
    if template=='labeled':return 'query: '+query+'\nInstruction: '+instruction
    raise ValueError(template)


def main():
    p=argparse.ArgumentParser();p.add_argument('--groups',default='/task/public/dev-groups.json');p.add_argument('--cache',default='/app/baseline-cache');args=p.parse_args()
    cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(16);torch.manual_seed(20261019)
    tok=AutoTokenizer.from_pretrained('/task/models/e5-large-v2',local_files_only=True)
    model=AutoModel.from_pretrained('/task/models/e5-large-v2',local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval()
    texts=[];keys=[]
    for subset in ['robust04','core17','news21']:
        for l in Path(f'/task/corpus/{subset}.jsonl').read_text().splitlines():
            r=json.loads(l);keys.append(subset+'/'+str(r['_id']));texts.append('passage: '+(r['title']+' '+r['text']).strip())
    if not (cache/'documents.npy').exists():
        arr=np.lib.format.open_memmap(cache/'documents.npy',mode='w+',dtype='float32',shape=(len(texts),1024))
        for start in range(0,len(texts),32):
            arr[start:start+32]=encode(model,tok,texts[start:start+32],32)
            if start%4800==0:print('encoded',start,'/',len(texts),flush=True)
        arr.flush();(cache/'keys.json').write_text(json.dumps(keys))
    if json.loads((cache/'keys.json').read_text())!=keys:raise ValueError('Baseline cache row mapping does not match fixed corpus')
    docs=np.load(cache/'documents.npy',mmap_mode='r');index={k:i for i,k in enumerate(keys)}
    if docs.shape!=(len(keys),1024):raise ValueError('Invalid baseline cache')
    groups=json.loads(Path(args.groups).read_text());reports={}
    for template in ['labeled']:
        vectors=encode(model,tok,[format_input(g['query'],g['instruction_'+v],template) for g in groups for v in ['og','changed']],1)
        ranks={}
        for i,g in enumerate(groups):
            mat=docs[[index[g['subset']+'/'+d] for d in g['candidates']]]
            ranks[g['key']]=[[g['candidates'][j] for j in np.argsort(-(mat@vectors[2*i+v]),kind='stable')] for v in range(2)]
        reports[template]=evaluate_pairs(groups,ranks)
        print(template,'H',reports[template]['H'],'P',reports[template]['P'],flush=True)
    (cache/'public-baselines.json').write_text(json.dumps(reports,indent=2))

if __name__=='__main__':main()
