import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from safetensors.numpy import save_file
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environment/runtime'))
import models

class CheckpointTests(unittest.TestCase):
    def fixture(self,d):
        base=d/'base';base.mkdir();sub=d/'submission';sub.mkdir();tower=sub/'tower';tower.mkdir()
        config={'model_type':'bert','hidden_size':1024,'max_position_embeddings':512}
        (base/'config.json').write_text(json.dumps(config))
        save_file({'weight':np.ones((2,3),dtype=np.float32)},base/'model.safetensors')
        (tower/'adapter_config.json').write_text(json.dumps({'peft_type':'LORA','r':1,'target_modules':['query']}))
        save_file({'lora_A.weight':np.ones((1,2),dtype=np.float32)},tower/'adapter_model.safetensors')
        (sub/'submission.json').write_text(json.dumps({'query_checkpoint':'tower','document_checkpoint':'base'}))
        return base,sub,tower
    def test_standard_lora_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d))
            with patch.object(models,'BASE',base):self.assertEqual(models.validate(sub)['query_checkpoint'],'tower')
    def test_base_only_submission(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));shutil.rmtree(tower)
            (sub/'submission.json').write_text(json.dumps({'query_checkpoint':'base','document_checkpoint':'base'}))
            with patch.object(models,'BASE',base):self.assertEqual(models.validate(sub)['query_checkpoint'],'base')
    def test_full_checkpoint_not_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d))
            (tower/'adapter_config.json').unlink();(tower/'adapter_model.safetensors').unlink()
            shutil.copy(base/'config.json',tower/'config.json');shutil.copy(base/'model.safetensors',tower/'model.safetensors')
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'standard LoRA'):models.validate(sub)
    def test_payload_counts_json_at_exact_byte_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));manifest=sub/'submission.json'
            total=sum(p.stat().st_size for p in sub.rglob('*') if p.is_file())
            with manifest.open('a') as f:f.write(' '*(models.MAX_DEPLOY_BYTES-total))
            with patch.object(models,'BASE',base):models.validate(sub)
            with manifest.open('a') as f:f.write(' ')
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'512 KiB'):models.validate(sub)
    def test_optional_markdown_not_deployed_payload(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(sub/'README.md').write_text('x'*(2*models.MAX_DEPLOY_BYTES))
            with patch.object(models,'BASE',base):models.validate(sub)
    def test_quantized_and_float64_headers_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d))
            for dtype in [np.int8,np.uint8,np.float64]:
                with self.subTest(dtype=dtype):
                    save_file({'lora_A.weight':np.ones((1,2),dtype=dtype)},tower/'adapter_model.safetensors')
                    with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'FP16/BF16/FP32'):models.validate(sub)
    def test_float16_and_bfloat16_headers_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));save_file({'lora_A.weight':np.ones((1,2),dtype=np.float16)},tower/'adapter_model.safetensors')
            with patch.object(models,'BASE',base):models.validate(sub)
            import torch
            from safetensors.torch import save_file as save_torch
            save_torch({'lora_A.weight':torch.ones((1,2),dtype=torch.bfloat16)},tower/'adapter_model.safetensors')
            with patch.object(models,'BASE',base):models.validate(sub)
    def test_modified_document_tower_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(sub/'submission.json').write_text(json.dumps({'query_checkpoint':'base','document_checkpoint':'tower'}))
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'document tower is fixed'):models.validate(sub)
    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(sub/'submission.json').write_text(json.dumps({'query_checkpoint':'../base','document_checkpoint':'base'}))
            with patch.object(models,'BASE',base),self.assertRaises(ValueError):models.validate(sub)
    def test_untrusted_adapter_type_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(tower/'adapter_config.json').write_text(json.dumps({'peft_type':'CUSTOM'}))
            with patch.object(models,'BASE',base),self.assertRaises(ValueError):models.validate(sub)
    def test_layer_replication_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(tower/'adapter_config.json').write_text(json.dumps({'peft_type':'LORA','layer_replication':[[0,24]]}))
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'layer_replication'):models.validate(sub)
    def test_symlink_root_and_entries_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);base,sub,tower=self.fixture(d);(sub/'alias').symlink_to(base)
            with patch.object(models,'BASE',base),self.assertRaises(ValueError):models.validate(sub)
            link=d/'link';link.symlink_to(sub)
            with self.assertRaises(ValueError):models.validate(link)
    def test_submitted_code_rejected_without_import(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));(sub/'encoder.py').write_text('raise RuntimeError("must never execute")\n')
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'only safetensors'):models.validate(sub)
    def test_custom_tokenizer_field_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base,sub,tower=self.fixture(Path(d));a=json.loads((sub/'submission.json').read_text());a['tokenizer']='base';(sub/'submission.json').write_text(json.dumps(a))
            with patch.object(models,'BASE',base),self.assertRaisesRegex(ValueError,'tokenizer and serving code are fixed'):models.validate(sub)

if __name__=='__main__':unittest.main()
