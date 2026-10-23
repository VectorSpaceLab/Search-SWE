"""Check the fixed serving contract, including padding and token prefixes."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import torch
import torch.nn.functional as F
from transformers import BatchEncoding

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'environment/runtime'))
from standard_encoder import Encoder


class Tokenizer:
    def __call__(self, texts, **kwargs):
        self.texts, self.options = texts, kwargs
        width = len(texts)+1
        ids = torch.zeros((len(texts), width), dtype=torch.long)
        mask = torch.zeros_like(ids)
        for i in range(len(texts)):
            ids[i, :i+2] = torch.arange(1, i+3)
            mask[i, :i+2] = 1
        return BatchEncoding({'input_ids':ids, 'attention_mask':mask})


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(1))
        self.calls = 0

    def forward(self, input_ids, attention_mask):
        self.calls += 1
        hidden = torch.zeros((*input_ids.shape, 1024), dtype=torch.bfloat16)
        hidden[..., 0] = input_ids
        hidden[..., 1] = 1
        hidden[attention_mask == 0] = 10000
        return SimpleNamespace(last_hidden_state=hidden)


class StandardEncoderTests(unittest.TestCase):
    def test_document_padding_is_excluded_before_float32_normalization(self):
        model, tok = Model(), Tokenizer()
        result = Encoder(model, tok, 'document').encode_documents(['first', 'second'])
        expected = torch.zeros((2, 1024))
        expected[:, 0] = torch.tensor([1.5, 2.])
        expected[:, 1] = 1
        self.assertTrue(torch.allclose(result, F.normalize(expected, dim=-1)))
        self.assertEqual(result.dtype, torch.float32)
        self.assertEqual(tok.texts, ['passage: first', 'passage: second'])

    def test_query_uses_one_fixed_formatted_forward(self):
        model, tok = Model(), Tokenizer()
        result = Encoder(model, tok, 'query').encode_query('query', 'instruction')
        self.assertEqual(model.calls, 1)
        self.assertEqual(tok.texts, ['query: query\nInstruction: instruction'])
        self.assertEqual(tok.options, dict(padding=True, truncation=True,
                                          max_length=512, return_tensors='pt'))
        self.assertEqual(result.shape, (1024,))
        self.assertAlmostEqual(float(result.norm()), 1., places=6)

    def test_role_and_empty_document_batch(self):
        model, tok = Model(), Tokenizer()
        self.assertEqual(Encoder(model, tok, 'document').encode_documents([]).shape, (0,1024))
        self.assertEqual(model.calls, 0)
        with self.assertRaises(ValueError):
            Encoder(model, tok, 'document').encode_query('q', 'i')
        with self.assertRaises(ValueError):
            Encoder(model, tok, 'query').encode_documents(['d'])


if __name__ == '__main__':
    unittest.main()
