"""Public fixed FP32 exhaustive MaxSim baseline; no approximate candidates."""
import ctypes
import json
from pathlib import Path
import sys

import numpy as np
from threadpoolctl import threadpool_limits


class ExactSearch:
    def __init__(self, corpus, threads=8, block_docs=16384, kernel='fused'):
        p = Path(corpus)
        self.offsets = np.fromfile(p / 'offsets.i64', dtype='<i8')
        self.vectors = np.memmap(p / 'vectors.f32', mode='r', dtype='<f4').reshape(-1, 128)
        self.ids = json.loads((p / 'ids.json').read_text())
        if len(self.ids) + 1 != len(self.offsets) or self.offsets[-1] != len(self.vectors):
            raise ValueError('Inconsistent corpus')
        self.threads, self.block_docs = threads, block_docs
        self.kernel = kernel
        self.limits = threadpool_limits(limits=threads)
        self.lib = ctypes.CDLL(str(Path(__file__).with_name('libmaxsim.so')))
        self.lib.reduce_maxsim.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64,
                                          ctypes.c_int64, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self.lib.reduce_maxsim.restype = None
        self.lib.exact_maxsim.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64,
                                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        self.lib.exact_maxsim.restype = None

    def search(self, query, k=100):
        q = np.asarray(query, dtype=np.float32)
        if q.ndim != 2 or q.shape[1] != 128 or not 1 <= len(q) <= 512:
            raise ValueError('Invalid query shape')
        scores = np.empty(len(self.ids), dtype=np.float32)
        if self.kernel == 'fused':
            if len(q) != 32:
                raise ValueError('The frozen kernel expects exactly 32 query tokens')
            self.lib.exact_maxsim(self.vectors.ctypes.data, self.offsets.ctypes.data,
                                 len(self.ids), q.ctypes.data, scores.ctypes.data, self.threads)
        else:
            for start in range(0, len(self.ids), self.block_docs):
                end = min(start + self.block_docs, len(self.ids))
                a, b = self.offsets[start], self.offsets[end]
                dots = self.vectors[a:b] @ q.T
                self.lib.reduce_maxsim(dots.ctypes.data, self.offsets[start:end+1].ctypes.data,
                                       end - start, int(a), len(q), scores[start:end].ctypes.data,
                                       self.threads)
        # Include all boundary ties before selecting by corpus row.
        k = min(k, len(scores))
        threshold = np.partition(scores, len(scores) - k)[len(scores) - k]
        selected = np.flatnonzero(scores >= threshold)
        selected = selected[np.lexsort((selected, -scores[selected]))[:k]]
        return selected, scores[selected]


def main():
    engine = None
    for line in sys.stdin:
        request = json.loads(line)
        if request['op'] == 'load':
            engine = ExactSearch(request['corpus'])
            result = {'ok': True}
        elif request['op'] == 'query':
            rows, scores = engine.search(request['vectors'])
            result = {'query_id': request['query_id'], 'results': [
                {'doc_id': engine.ids[i], 'score': float(s)} for i, s in zip(rows, scores)]}
        else:
            raise ValueError('Unknown operation')
        print(json.dumps(result, separators=(',', ':'), allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
