"""Mature public retriever: training-text routing and exact fixed-base fallback.

Routing parameters come from public development. All row sets, word statistics
and source surfaces are training-derived; every query's scores are recomputed.
"""
from collections import Counter, defaultdict
import math
import re
import numpy as np
import torch
from optimized_source import FixedBaseSource

_STOP = set('\na an and are as at be been being but by can could did do does for from has have how i in is it its\nlocated many name of on or only present reply say state the their them there they this to what where\nwhich who why will with without world you your answer short question give just country using nothing\nelse national capital day identify containing associated location found home explanation island visit explain not s\ntravel would situated landmark place city cities\n'.split())

_WORDS = re.compile('[a-z0-9]+')

def _token_set(text):
    return set(_WORDS.findall(text.casefold())) - _STOP


class MatureSource(FixedBaseSource):
    def __init__(self, args):
        torch.set_num_threads(1)
        super().__init__(args)
        self.doc_terms = []
        document_frequency = Counter()
        for row in self.rows:
            terms = _token_set(row["instruction"] + " " + row["input"] + " " + row["output"])
            self.doc_terms.append(terms)
            document_frequency.update(terms)
        n_docs = len(self.doc_terms)
        self.idf = {term: math.log((n_docs + 1) / (count + 1)) + 1.0
                    for term, count in document_frequency.items()}

    def _lexical_choice(self, query, pool):
        query_terms = _token_set(query['instruction'] + ' ' + query['input']) - _token_set(query['target_text'])
        query_terms &= self.idf.keys()
        if not query_terms:
            return None
        row_scores = np.zeros(len(pool['indices']), dtype=np.float32)
        surface_terms = defaultdict(set)
        surface_positions = defaultdict(list)
        for j, (index, surface) in enumerate(zip(pool['indices'], pool['surfaces'])):
            if surface:
                surface_positions[surface].append(j)
            hits = query_terms & self.doc_terms[int(index)]
            if not hits:
                continue
            row_scores[j] = sum((self.idf[w] for w in hits))
            surface_terms[surface].update((w for w in hits if self.idf[w] >= 3.0))
        aggregates = {}
        for surface, positions in surface_positions.items():
            values = sorted((float(row_scores[j]) for j in positions), reverse=True)
            aggregates[surface] = sum(values[:3])
        if not aggregates:
            return None
        ranked = sorted(aggregates, key=lambda s: (-aggregates[s], s))
        best = ranked[0]
        next_score = aggregates[ranked[1]] if len(ranked) > 1 else 0.0
        positions = surface_positions[best]
        supported = surface_terms[best]
        if len(supported) < 1 or len(positions) < 10 or aggregates[best] < 1.0 or (aggregates[best] < 1.12 * max(next_score, 1e-06)):
            return None
        _, fixed = self.training.pool(query['target_text'])
        indices = pool['indices']
        positions.sort(key=lambda j: (-float(row_scores[j]), -float(fixed[j][5]), self.ids[int(indices[j])]))
        return [self.ids[int(indices[j])] for j in positions[:10]]

    def rank(self, query, action="query"):
        if action != "query":
            raise ValueError("This starting implementation exposes retrieval only")
        pool = self.coherence.pool(query["target_text"])
        lexical = self._lexical_choice(query, pool)
        if lexical is not None:
            return {"query_id":query["id"], "ids":lexical}
        return super().rank(query, action)
