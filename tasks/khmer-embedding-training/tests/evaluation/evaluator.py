#!/usr/bin/env python3
"""Fixed e5 mean-pooling encoder, exact search, and optional public MKQA scoring."""
import argparse
import json
import os
from pathlib import Path
import time
import unicodedata

# Do not use the network or dynamically import any submitted code.
os.environ["HF_HUB_OFFLINE"]="1"
os.environ["TRANSFORMERS_OFFLINE"]="1"
os.environ["TOKENIZERS_PARALLELISM"]="false"
import numpy as np
import pyarrow.parquet as pq
import torch
from transformers import AutoModel,AutoTokenizer
from checkpoint import validate_checkpoint
from metrics import read_jsonl,score_results

def parser():
 p=argparse.ArgumentParser()
 p.add_argument("--checkpoint",required=True,type=Path)
 p.add_argument("--backbone",type=Path,default=Path("/task/models/multilingual-e5-large"))
 p.add_argument("--corpus",type=Path,default=Path("/task/data/corpus.parquet"))
 p.add_argument("--queries",type=Path,default=Path("/task/data/validation/queries.jsonl"))
 p.add_argument("--answers",type=Path)
 p.add_argument("--output",required=True,type=Path)
 p.add_argument("--work-dir",required=True,type=Path)
 p.add_argument("--retrieval-only",action="store_true")
 return p

def encode_tokens(model,encoded,device):
 encoded=encoded.to(device)
 with torch.inference_mode():
  hidden=model(**encoded).last_hidden_state.float()
  mask=encoded.attention_mask.unsqueeze(-1).bool()
  pooled=hidden.masked_fill(~mask,0).sum(1)/mask.sum(1).clamp_min(1)
  lengths=torch.linalg.vector_norm(pooled,dim=1)
  if not torch.isfinite(pooled).all() or (lengths<=0).any():raise ValueError("Nonfinite or zero embedding")
  return torch.nn.functional.normalize(pooled,p=2,dim=1)

def encode(model,tokenizer,texts,device):
 return encode_tokens(model,tokenizer(texts,padding=True,truncation=True,max_length=512,return_tensors="pt"),device)

def topk_stable(scores,indices,k):
 # First order by corpus position, then stable-sort by descending score.
 order=torch.argsort(indices,dim=1,stable=True)
 scores=torch.gather(scores,1,order);indices=torch.gather(indices,1,order)
 order=torch.argsort(scores,dim=1,descending=True,stable=True)[:,:k]
 return torch.gather(scores,1,order),torch.gather(indices,1,order)

def main():
 a=parser().parse_args()
 start=time.monotonic()
 validate_checkpoint(a.checkpoint,a.backbone)
 if not torch.cuda.is_available():raise RuntimeError("This evaluation requires the assigned NVIDIA GPU")
 torch.set_num_threads(8)
 torch.backends.cuda.matmul.allow_tf32=False
 torch.backends.cudnn.allow_tf32=False
 device=torch.device("cuda:0")
 tokenizer=AutoTokenizer.from_pretrained(a.checkpoint,local_files_only=True,trust_remote_code=False)
 model=AutoModel.from_pretrained(a.checkpoint,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,attn_implementation="sdpa").to(device).eval()
 queries=read_jsonl(a.queries)
 if not queries or len({q["id"] for q in queries})!=len(queries) or any(not isinstance(q["question"],str) or not q["question"].strip() for q in queries):raise ValueError("Invalid queries")
 qvec=torch.cat([encode(model,tokenizer,["query: "+q["question"] for q in queries[s:s+32]],device) for s in range(0,len(queries),32)])
 pf=pq.ParquetFile(a.corpus)
 n=pf.metadata.num_rows
 if n<1:raise ValueError("Empty corpus")
 a.work_dir.mkdir(parents=True,exist_ok=True)
 # The verifier generates this index afresh from the submitted checkpoint.
 vectors=np.lib.format.open_memmap(a.work_dir/"vectors.npy",mode="w+",dtype=np.float32,shape=(n,1024))
 offset=0
 for batch in pf.iter_batches(batch_size=4096,columns=["title","text"]):
  d=batch.to_pydict()
  texts=["passage: "+unicodedata.normalize("NFD",(title+"\n"+text).lower()) for title,text in zip(d["title"],d["text"])]
  encoded=tokenizer(texts,truncation=True,max_length=512,padding=False)
  order=sorted(range(batch.num_rows),key=lambda i:len(encoded["input_ids"][i]))
  for first in range(0,len(order),128):
   chosen=order[first:first+128]
   features=[{name:values[i] for name,values in encoded.items()} for i in chosen]
   padded=tokenizer.pad(features,padding=True,return_tensors="pt")
   v=encode_tokens(model,padded,device).cpu().numpy()
   vectors[np.asarray(chosen)+offset]=v
  offset+=batch.num_rows
  if offset%40960==0 or offset==n:print(json.dumps({"phase":"encode_corpus","done":offset,"total":n,"seconds":round(time.monotonic()-start,1)}),flush=True)

 vectors.flush()
 del model
 torch.cuda.empty_cache()
 all_results=[]
 k=min(100,n)
 for qstart in range(0,len(queries),32):
  qbatch=qvec[qstart:qstart+32]
  best_score=torch.empty((len(qbatch),0),device=device,dtype=torch.float32)
  best_idx=torch.empty((len(qbatch),0),device=device,dtype=torch.int64)
  for start_doc in range(0,n,16384):
   v=torch.as_tensor(np.array(vectors[start_doc:start_doc+16384]),device=device)
   scores=qbatch@v.T
   # At most k values from a block can survive global top-k. Stable ties use corpus position.
   order=torch.argsort(scores,dim=1,descending=True,stable=True)[:,:k]
   local_score=torch.gather(scores,1,order);local_idx=order+start_doc
   best_score,best_idx=topk_stable(torch.cat([best_score,local_score],1),torch.cat([best_idx,local_idx],1),k)
  for q,idx,score in zip(queries[qstart:qstart+32],best_idx.cpu().tolist(),best_score.cpu().tolist()):
   all_results.append({"id":q["id"],"indices":idx,"scores":score})
 a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text("".join(json.dumps(row,allow_nan=False)+"\n" for row in all_results))
 if not a.retrieval_only:
  answer_path=a.answers
  if answer_path is None and a.queries==Path("/task/data/validation/queries.jsonl"):
   answer_path=Path("/task/data/validation/answers.jsonl")
  labels=read_jsonl(answer_path) if answer_path else queries
  report=score_results(a.corpus,queries,labels,all_results)
  report.update({"seconds":time.monotonic()-start,"checkpoint":str(a.checkpoint),"encoding":"e5-mean-nfd-lower-bf16-v1"})
  a.output.with_suffix(".metrics.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
  print(json.dumps({k:v for k,v in report.items() if k!="per_query"}),flush=True)
if __name__=="__main__":main()
