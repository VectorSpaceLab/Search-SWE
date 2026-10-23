"""Rank training records from current fixed-probe source probabilities."""


import numpy as np

from retrieval_index import Retriever


class EfficientSource(Retriever):
    def probabilities(self, query):
        raise NotImplementedError("Provide fixed-probe probabilities; use build_starter.py for the complete system")

    def rank(self, query, action="query"):
        if action != "query":
            raise ValueError("This starting implementation exposes retrieval only")
        probability = self.probabilities(query)
        masses = np.bincount(self.query_source.token_buckets, weights=probability,
                             minlength=len(self.query_source.surface_indices)+1)
        pool = self.coherence.pool(query["target_text"])
        scores = np.asarray([masses[self.query_source.surface_indices[s]]
                             if s in self.query_source.surface_indices else 0.
                             for s in pool["surfaces"]], dtype=np.float64)
        ids = np.asarray([self.ids[i] for i in pool["indices"]])
        order = np.lexsort((ids, -scores))[:10]
        return {"query_id": query["id"], "ids": ids[order].tolist()}
