"""Budget-feasible GPU execution of fixed full-table filtering and exact Top-k."""
import numpy as np
import torch
from metrics import PROPERTIES,TARGETS


class TensorTables:
    def __init__(self,properties,scores,membership=None):
        if not torch.cuda.is_available() or torch.cuda.device_count()!=1:
            raise RuntimeError('One mapped CUDA GPU is required')
        self.properties=torch.as_tensor(properties.T,device='cuda').contiguous()
        self.scores=torch.as_tensor(scores.T,device='cuda').contiguous()
        self.n=self.scores.shape[1]
        self.membership=(torch.as_tensor(membership,device='cuda') if membership is not None else None)

    def search(self,query):
        score=self.scores[TARGETS.index(query['target'])]
        mask=torch.isfinite(score)
        if self.membership is not None:mask &= self.membership
        for name,(lower,upper) in query['constraints'].items():
            if lower is None and upper is None:continue
            values=self.properties[PROPERTIES.index(name)]
            mask &= torch.isfinite(values)
            if lower is not None:mask &= values>=lower
            if upper is not None:mask &= values<=upper
        masked=score.masked_fill(~mask,float('inf'))
        k=min(query['k'],self.n)
        if k==0:return []
        boundary=torch.topk(masked,k,largest=False,sorted=False).values.max()
        if not torch.isfinite(boundary).item():
            chosen=torch.nonzero(mask,as_tuple=True)[0]
        else:
            below=torch.nonzero(masked<boundary,as_tuple=True)[0]
            tied=torch.nonzero(masked==boundary,as_tuple=True)[0].sort().values
            chosen=torch.cat((below,tied[:k-below.numel()]))
        return chosen.cpu().tolist()
