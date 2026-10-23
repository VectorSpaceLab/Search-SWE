"""Exact fixed 7B inference from the supplied compact diagnostic probe."""
from types import SimpleNamespace
import numpy as np
import torch
from efficient_source import EfficientSource
from compact_probe import load_probe
from query_source_features import QuerySourceFeatures
from retrieval_index import Retriever

class FixedBaseSource(EfficientSource):
    def __init__(self, args):
        options = dict(vars(args), mode="source-mode")
        Retriever.__init__(self, SimpleNamespace(**options))
        self.probe = load_probe(args.model_dir / "base")
        self.model = self.probe
        self.cpu_embedding = self.probe.cpu_embedding
        self.query_source = QuerySourceFeatures(self)
        self.head_pools = {}

    def probabilities(self, query):
        # All selected output rows are fixed-model, training-derived vocabulary
        # features. Query hidden states/logits/probabilities are never retained.
        key = query["target_text"].strip().casefold()
        if key not in self.head_pools:
            pool = self.coherence.pool(query["target_text"])
            buckets = [self.query_source.surface_indices[s] for s in pool["counts"]
                       if s in self.query_source.surface_indices]
            token_ids = np.flatnonzero(np.isin(self.query_source.token_buckets, buckets))
            rows = self.probe.output_rows(token_ids).to("cuda", dtype=torch.bfloat16)
            self.head_pools[key] = token_ids, rows
        token_ids, rows = self.head_pools[key]
        ids_cpu = torch.tensor([query["input_ids"]], dtype=torch.long)
        positions = torch.tensor(query["target_token_indices"], device="cuda", dtype=torch.long)
        actual = ids_cpu[0, query["target_token_indices"]].to("cuda")
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            embedded = torch.nn.functional.embedding(ids_cpu, self.cpu_embedding).to("cuda", dtype=torch.bfloat16)
            hidden = self.model.model(inputs_embeds=embedded, attention_mask=torch.ones_like(ids_cpu, device="cuda"),
                                      use_cache=False).last_hidden_state[0, positions-1]
            alternative_logits = torch.nn.functional.linear(hidden, rows).float()
            if len(positions) > 1:
                actual_rows = self.probe.output_rows(actual.cpu()).to("cuda", dtype=torch.bfloat16)
                actual_logits = (hidden.float()*actual_rows.float()).sum(-1)
                # Choose the span position with strongest candidate-source
                # evidence against the erroneous token. This retrieval-specific
                # likelihood ratio avoids a full CPU vocabulary projection.
                losses = torch.logsumexp(alternative_logits, dim=1)-actual_logits
                chosen = int(losses.argmax())
            else:
                chosen = 0
            # The full-vocabulary denominator cancels in the source ranking.
            # Multi-token selection uses the source-candidate ratio above,
            # rather than claiming exact full-vocabulary CE equivalence.
            values = alternative_logits[chosen].softmax(-1).cpu().numpy()
        result = np.zeros(self.model.config.vocab_size, dtype=np.float64)
        result[token_ids] = values
        torch.cuda.synchronize()
        return result
