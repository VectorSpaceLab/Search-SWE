"""Trusted current-query oracle. No arbitrary query vector or ANN interface."""
import time
import numpy as np


class QueryFailure(RuntimeError):
    pass


class Oracle:
    def __init__(self, vectors, budget=200, clock=time.monotonic):
        self.vectors, self.budget, self.clock = vectors, budget, clock
        self.current = None
        self.used = 0
        self.failed = False

    def begin(self, query, token, deadline):
        self.current = np.asarray(query, dtype=np.float32)
        if self.current.shape != (self.vectors.shape[1],) or not np.isfinite(self.current).all():
            raise ValueError('Invalid trusted query vector')
        self.token, self.deadline, self.used, self.failed = token, deadline, 0, False

    def close(self):
        self.current = None

    def score(self, request):
        try:
            if self.current is None:
                raise QueryFailure('Scoring unavailable outside an active query')
            if self.failed or self.clock() > self.deadline:
                raise QueryFailure('Query expired or already invalid')
            if set(request) != {'op', 'token', 'doc_ids'} or request['op'] != 'score':
                raise QueryFailure('Invalid scoring request')
            if request['token'] != self.token:
                raise QueryFailure('Request does not belong to current query')
            ids = request['doc_ids']
            if not isinstance(ids, list) or not ids:
                raise QueryFailure('doc_ids must be a nonempty list')
            # Charge every requested document, including duplicates and rejected overages.
            self.used += len(ids)
            if self.used > self.budget:
                raise QueryFailure('Expensive-score budget exceeded')
            rows = []
            for doc in ids:
                if (not isinstance(doc, str) or not 3 < len(doc) <= 3+len(str(len(self.vectors)-1))
                        or not doc.startswith('doc') or not doc[3:].isascii() or not doc[3:].isdigit()):
                    raise QueryFailure('Unknown document ID')
                row = int(doc[3:])
                if doc != f'doc{row}' or not 0 <= row < len(self.vectors):
                    raise QueryFailure('Unknown document ID')
                rows.append(row)
            delta = np.asarray(self.vectors[rows], dtype=np.float64) - self.current.astype(np.float64)
            distances = np.sqrt(np.einsum('ij,ij->i', delta, delta, dtype=np.float64))
            if self.clock() > self.deadline:
                raise QueryFailure('Query timeout during scoring')
            return {'op': 'scores', 'token': self.token, 'distances': distances.tolist(),
                    'used': self.used, 'remaining': self.budget - self.used}
        except QueryFailure:
            self.failed = True
            raise
