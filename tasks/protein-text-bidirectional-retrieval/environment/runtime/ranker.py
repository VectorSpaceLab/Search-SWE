"""Author-only draft trusted ranking core; no task-package change."""
import numpy as np

DIMENSION = 64
POOL_SIZE = 10000


def normalized(values, shape):
    values = np.asarray(values)
    if values.shape != shape or values.dtype.kind not in 'fiu':
        raise ValueError('Expected the fixed numeric embedding shape')
    with np.errstate(over='ignore', invalid='ignore'):
        values = values.astype(np.float32)
    if not np.isfinite(values).all():
        raise ValueError('Embedding values must be finite float32 numbers')
    # Float64 accumulation prevents overflow for legal large float32 inputs.
    norms = np.linalg.norm(values.astype(np.float64), axis=-1, keepdims=True)
    return np.divide(values, norms, out=np.zeros_like(values), where=norms != 0)


class Ranker:
    def __init__(self, candidate_ids, candidate_vectors):
        if (len(candidate_ids) != POOL_SIZE or len(set(candidate_ids)) != POOL_SIZE
                or any(not isinstance(x, str) for x in candidate_ids)):
            raise ValueError('Expected10000 unique string candidate IDs')
        self.ids = np.asarray(candidate_ids)
        self.vectors = normalized(candidate_vectors, (POOL_SIZE, DIMENSION))

    def search(self, query_vector):
        if query_vector is None:
            return []
        query = normalized(query_vector, (DIMENSION,))
        if not np.any(query):
            return []
        scores = self.vectors @ query
        order = np.lexsort((self.ids, -scores))[:20]
        return self.ids[order].tolist()
