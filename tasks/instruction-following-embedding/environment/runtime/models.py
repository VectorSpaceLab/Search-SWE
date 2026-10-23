"""Validate compact standard LoRA query submissions for the fixed E5 service."""
import json
from pathlib import Path
from safetensors import safe_open

BASE=Path('/task/models/e5-large-v2')
MAX_DEPLOY_BYTES=512*1024
WEIGHT_DTYPES={'F16','BF16','F32'}


def safe_dir(root,name):
    if name=='base':return BASE
    if not isinstance(name,str) or not name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe checkpoint directory')
    path=root/name
    if not path.is_dir() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Checkpoint is outside submission')
    return path


def validate(root):
    if root.is_symlink() or not root.is_dir():raise ValueError('Missing regular submission directory')
    payload=0;weights=[]
    for p in root.rglob('*'):
        if p.is_symlink() or not (p.is_dir() or p.is_file()):raise ValueError('Special files and symlinks are forbidden')
        if p.is_file():
            if p.suffix not in {'.json','.safetensors','.md'}:
                raise ValueError('Submit only safetensors weights, JSON configuration and optional Markdown documentation')
            if p.suffix!='.md':payload+=p.stat().st_size
            if p.suffix=='.safetensors':weights.append(p)
    if payload>MAX_DEPLOY_BYTES:
        raise ValueError(f'Query deployment payload is {payload} bytes; limit is 512 KiB ({MAX_DEPLOY_BYTES} bytes), including all weights and JSON')
    config=json.loads((root/'submission.json').read_text())
    if set(config)!={'query_checkpoint','document_checkpoint'}:
        raise ValueError('Only query_checkpoint and document_checkpoint are accepted; the tokenizer and serving code are fixed')
    if config['document_checkpoint']!='base':
        raise ValueError('The document tower is fixed; document_checkpoint must be base')
    path=safe_dir(root,config['query_checkpoint'])
    if path!=BASE:
        if not (path/'adapter_config.json').is_file() or not (path/'adapter_model.safetensors').is_file():
            raise ValueError('The query checkpoint must be base or a standard LoRA adapter; full checkpoints are not deployed')
        adapter=json.loads((path/'adapter_config.json').read_text())
        if adapter.get('peft_type')!='LORA' or any(adapter.get(k) for k in ('auto_mapping','modules_to_save','layer_replication')):
            raise ValueError('Use standard LoRA without auto_mapping, modules_to_save or layer_replication')
    for p in weights:
        with safe_open(p,framework='pt',device='cpu') as handle:
            if any(handle.get_slice(k).get_dtype() not in WEIGHT_DTYPES for k in handle.keys()):
                raise ValueError('Deployment weights must use unquantized FP16/BF16/FP32 safetensors tensors')
    return config


def load(root,name,device):
    import torch
    from transformers import AutoModel,AutoConfig
    path=safe_dir(root,name)
    adapter=(path/'adapter_config.json').exists()
    config=AutoConfig.from_pretrained(BASE,local_files_only=True,trust_remote_code=False)
    model=AutoModel.from_pretrained(BASE if adapter else path,config=config,use_safetensors=True,local_files_only=True,trust_remote_code=False,
                                   dtype=torch.bfloat16,attn_implementation='sdpa')
    if adapter:
        from peft import PeftModel
        model=PeftModel.from_pretrained(model,path,local_files_only=True,is_trainable=False)
        model=model.merge_and_unload()
    for p in model.parameters():
        if not torch.isfinite(p).all():raise ValueError('Nonfinite model parameters')
    return model.to(device).eval()
