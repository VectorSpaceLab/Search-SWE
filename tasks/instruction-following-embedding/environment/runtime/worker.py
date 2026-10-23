"""Persistent, isolated encoding worker. Uses only one independent tower per process."""
import contextlib
import json
import os
from pathlib import Path
import sys

# Libraries print startup messages; reserve stdout for framed vector responses.
wire=sys.stdout
with contextlib.redirect_stdout(sys.stderr):
    import numpy as np
    import torch
    from transformers import AutoTokenizer
    from models import BASE,load
    torch.set_num_threads(16)
    torch.manual_seed(0)
    root=Path('/app/submission')
    role=sys.argv[1]
    config=json.loads((root/'submission.json').read_text())
    model=load(root,config[role+'_checkpoint'],'cuda')
    tok=AutoTokenizer.from_pretrained(BASE,local_files_only=True,trust_remote_code=False)
    from standard_encoder import Encoder
    from forward_budget import ForwardBudget
    budget=ForwardBudget(model) if role=='query' else None
    # Establish CUDA with trusted loader code before restricting filesystem reads.
    # Only trusted serving code is used; no submitted Python is imported.
    from isolation import isolate
    from isolation import UID
    scratch=Path(os.environ['ENCODER_WORK_DIR'])
    for p in scratch.rglob('*'):os.chown(p,UID,UID,follow_symlinks=False)
    isolate(str(scratch))
    encoder=Encoder(model,tok,role)
    versions=[p._version for p in model.parameters()]
print(json.dumps({'ready':True}),file=wire,flush=True)
for line in sys.stdin:
    try:
        request=json.loads(line)
        with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
            if role=='document':result=encoder.encode_documents(request['texts'])
            else:
                budget.begin()
                result=encoder.encode_query(request['query'],request['instruction'])
                budget.finish()
            if isinstance(result,torch.Tensor):result=result.detach().float().cpu().numpy()
            result=np.asarray(result,dtype=np.float32)
            expected=(len(request['texts']),1024) if role=='document' else (1024,)
            if result.shape!=expected or not np.isfinite(result).all() or np.any(np.linalg.norm(result,axis=-1)==0):
                raise ValueError('Vectors must be finite, nonzero and have shape '+str(expected))
            if any(p._version!=v for p,v in zip(model.parameters(),versions)):raise ValueError('Test-time model mutation')
            torch.cuda.synchronize()
        reply={'vectors':result.tolist()}
    except Exception as exc:
        reply={'error':type(exc).__name__+': '+str(exc)[:500]}
    if any(p._version!=v for p,v in zip(model.parameters(),versions)):
        reply={'error':'Test-time model mutation','model_violation':True}
    if budget is not None and budget.violation:
        reply={'error':'Query must use one complete E5 forward on one <=512-token sequence', 'model_violation':True}
    print(json.dumps(reply,allow_nan=False,separators=(',',':')),file=wire,flush=True)
