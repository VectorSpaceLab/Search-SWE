"""Query cost contracts, including repeated, batched, partial and tampered passes."""
from pathlib import Path
import sys
import unittest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'environment/runtime'))
from forward_budget import ForwardBudget


class TinyBert(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embeddings = torch.nn.Embedding(32, 2)
        self.encoder = torch.nn.Module()
        self.encoder.layer = torch.nn.ModuleList([torch.nn.Linear(2, 2) for _ in range(2)])

    def forward(self, input_ids, attention_mask=None, inputs_embeds=None):
        x = self.embeddings(input_ids)
        for layer in self.encoder.layer:
            x = layer(x)
        return x


class ForwardBudgetTests(unittest.TestCase):
    def setUp(self):
        self.model = TinyBert()
        self.budget = ForwardBudget(self.model)
        self.ids = torch.ones((1, 10), dtype=torch.long)

    def test_one_complete_pass_and_reset(self):
        for _ in range(2):
            self.budget.begin()
            self.model(input_ids=self.ids, attention_mask=torch.ones_like(self.ids))
            self.budget.finish()
        self.assertFalse(self.budget.violation)

    def test_repeated_pass_and_sticky_failure(self):
        self.budget.begin()
        self.model(self.ids)
        with self.assertRaises(ValueError):
            self.model(self.ids)
        with self.assertRaises(ValueError):
            self.budget.begin()

    def test_batch_and_length_are_bounded(self):
        for shape in [(2, 10), (1, 513)]:
            model = TinyBert(); budget = ForwardBudget(model); budget.begin()
            with self.assertRaises(ValueError):
                model(torch.ones(shape, dtype=torch.long))
            self.assertTrue(budget.violation)

    def test_no_partial_or_missing_backbone(self):
        self.budget.begin()
        self.model.embeddings(self.ids)
        with self.assertRaises(ValueError):
            self.budget.finish()

    def test_no_block_attention_or_nonbinary_mask(self):
        for mask in [torch.ones(1, 10, 10), torch.full((1, 10), 2)]:
            model = TinyBert(); budget = ForwardBudget(model); budget.begin()
            with self.assertRaises(ValueError):
                model(input_ids=self.ids, attention_mask=mask)

    def test_removed_hook_is_rejected(self):
        self.budget.begin()
        self.model(self.ids)
        self.budget.hooks[-1][2].remove()
        with self.assertRaises(ValueError):
            self.budget.finish()

    def test_skipping_a_layer_is_rejected(self):
        self.model.encoder.layer[-1] = torch.nn.Identity()
        self.budget.begin()
        self.model(self.ids)
        with self.assertRaises(ValueError):
            self.budget.finish()

    def test_repeating_a_layer_inside_one_backbone_call_is_rejected(self):
        def repeated(input_ids):
            x = self.model.embeddings(input_ids)
            return self.model.encoder.layer[0](self.model.encoder.layer[0](x))
        self.model.forward = repeated
        self.budget.begin()
        with self.assertRaises(ValueError):
            self.model(self.ids)
        self.assertTrue(self.budget.violation)


if __name__ == '__main__':
    unittest.main()
