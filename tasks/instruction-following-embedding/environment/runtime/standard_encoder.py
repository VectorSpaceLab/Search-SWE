"""The fixed E5 serving interface; submissions supply checkpoint weights only."""
import torch
import torch.nn.functional as F


class Encoder:
    def __init__(self, model, tokenizer, role):
        self.model = model
        self.tokenizer = tokenizer
        self.role = role
        self.device = next(model.parameters()).device

    def _encode(self, texts):
        batch = self.tokenizer(texts, padding=True, truncation=True,
                               max_length=512, return_tensors='pt').to(self.device)
        hidden = self.model(**batch).last_hidden_state.float()
        mask = batch['attention_mask'].unsqueeze(-1).float()
        return F.normalize((hidden * mask).sum(1) / mask.sum(1), dim=-1)

    def encode_documents(self, texts):
        if self.role != 'document':
            raise ValueError('Document encoding requires the document tower')
        if not texts:
            return torch.empty((0, 1024), device=self.device, dtype=torch.float32)
        return self._encode(['passage: '+text for text in texts])

    def encode_query(self, query, instruction):
        if self.role != 'query':
            raise ValueError('Query encoding requires the query tower')
        return self._encode(['query: '+query+'\nInstruction: '+instruction])[0]
