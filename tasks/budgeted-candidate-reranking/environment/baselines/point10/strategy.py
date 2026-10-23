import json,sys,math
q=json.loads(sys.stdin.readline());docs=q['candidates'];remaining=q['token_budget']
MODE='point'
N=10
def call(m):
 print(json.dumps(m),flush=True)
 r=json.loads(sys.stdin.readline())
 return r
if MODE=='bm25':
 ids=[d['doc_id'] for d in docs[:10]]
elif MODE=='point':
 values={}
 for d in docs[:N]:
  prompt='Query: '+q['query']+'\nPassage: '+d['text']+'\nDoes the passage answer the query? Reply Yes or No.'
  m={'type':'count','messages':[{'role':'user','content':prompt}],'max_new_tokens':1,'logprob_tokens':['Yes','No'],'candidate_ids':[d['doc_id']]}
  c=call(m)
  if c['reserved_cost']>remaining:break
  m['type']='generate';r=call(m);remaining=r['remaining_tokens']
  lp=r['first_token_logprobs'];values[d['doc_id']]=lp['Yes']-lp['No']
 # Fixed tail stays after all scored head documents.
 head=sorted([d for d in docs if d['doc_id'] in values],key=lambda d:(-values[d['doc_id']],d['rank']))
 tail=[d for d in docs if d['doc_id'] not in values]
 ids=[d['doc_id'] for d in head+tail][:10]
else:
 selected=docs[:N]
 while selected:
  prompt='Rank the following passages by relevance to the query: '+q['query']+'\n'
  prompt+='\n'.join('['+str(i+1)+'] '+d['text'] for i,d in enumerate(selected))
  prompt+='\nReturn all passage numbers in descending relevance, separated by commas. Output only numbers.'
  m={'type':'count','messages':[{'role':'user','content':prompt}],'max_new_tokens':max(20,len(selected)*3),'candidate_ids':[d['doc_id'] for d in selected]}
  c=call(m)
  if c['reserved_cost']<=remaining:break
  selected=selected[:-1]
 if selected:
  m['type']='generate';r=call(m)
  import re
  nums=[int(x)-1 for x in re.findall(r'\d+',r['text'])]
  order=[]
  for i in nums:
   if 0<=i<len(selected) and i not in order:order.append(i)
  order += [i for i in range(len(selected)) if i not in order]
  arranged=[selected[i] for i in order]+docs[len(selected):]
  ids=[d['doc_id'] for d in arranged[:10]]
 else:ids=[d['doc_id'] for d in docs[:10]]
print(json.dumps({'type':'result','ids':ids}),flush=True)
