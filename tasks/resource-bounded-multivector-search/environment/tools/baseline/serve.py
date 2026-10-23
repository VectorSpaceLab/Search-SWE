"""Optional fixed high-recall baseline; original-vector MaxSim reranking."""
import argparse
import ctypes
from pathlib import Path
import sys

import faiss
import numpy as np
import orjson


class Search:
    def __init__(self, corpus, index):
        corpus, index = Path(corpus), Path(index)
        self.offsets = np.fromfile(corpus/'offsets.i64', dtype='<i8')
        self.vectors = np.memmap(corpus/'vectors.f32', mode='r', dtype='<f4').reshape(-1, 128)
        self.ids = orjson.loads((corpus/'ids.json').read_bytes())
        self.documents = np.memmap(index/'token_doc.i32', mode='r', dtype='<i4')
        self.config = orjson.loads((index/'metadata.json').read_bytes())
        faiss.omp_set_num_threads(8)
        self.index = faiss.read_index(str(index/'tokens.faiss'))
        self.ivf = faiss.extract_index_ivf(self.index)
        self.ivf.nprobe = self.config['nprobe']
        self.ivf.max_codes = 0
        self.hits = self.config['candidate_tokens_per_query_token']
        self.library = ctypes.CDLL(str(Path(__file__).with_name('libcandidate.so')))
        self.library.score_candidates.argtypes = [ctypes.c_void_p]*3 + [ctypes.c_int64] + [ctypes.c_void_p]*2 + [ctypes.c_int]
        self.library.score_candidates.restype = None
        self.library.collect_candidates.argtypes = [ctypes.c_void_p]*2 + [ctypes.c_int64]*2 + [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p]
        self.library.collect_candidates.restype = ctypes.c_int64
        self.seen = np.zeros((len(self.ids)+63)//64, dtype=np.uint64)
        self.candidate_buffer = np.empty(len(self.ids), dtype=np.int32)
        if (self.index.ntotal != len(self.vectors) or len(self.documents) != len(self.vectors)
                or len(self.offsets) != len(self.ids)+1 or self.offsets[-1] != len(self.vectors)):
            raise ValueError('Baseline inputs do not match the complete corpus')
        # Loading may read the fixed corpus; no hidden query is available here.
        float(self.vectors.sum(dtype=np.float64))

    def candidates(self, query):
        _, tokens = self.index.search(query, self.hits)
        count = self.library.collect_candidates(self.documents.ctypes.data, tokens.ctypes.data,
            tokens.size, len(self.ids), self.seen.ctypes.data, len(self.seen), self.candidate_buffer.ctypes.data)
        return self.candidate_buffer[:count]

    def search(self, vectors):
        query = np.ascontiguousarray(vectors, dtype=np.float32)
        if query.shape != (32, 128) or not np.isfinite(query).all():
            raise ValueError('Expected finite 32x128 vectors')
        candidates = self.candidates(query)
        scores = np.empty(len(candidates), dtype=np.float32)
        self.library.score_candidates(self.vectors.ctypes.data, self.offsets.ctypes.data,
            candidates.ctypes.data, len(candidates), query.ctypes.data, scores.ctypes.data, 8)
        if len(candidates) > 100:
            threshold = np.partition(scores, len(scores)-100)[len(scores)-100]
            selected = np.flatnonzero(scores >= threshold)
        else:
            selected = np.arange(len(candidates))
        selected = selected[np.lexsort((candidates[selected], -scores[selected]))[:100]]
        return [{'doc_id': self.ids[int(candidates[i])], 'score': float(scores[i])} for i in selected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', help='Optional fixed public index instead of request index')
    args = parser.parse_args()
    engine = None
    for line in sys.stdin.buffer:
        request = None
        try:
            request = orjson.loads(line)
            if request['op'] == 'load':
                Path(request['work_dir']).mkdir(parents=True, exist_ok=True)
                engine = Search(request['corpus'], args.index or request['index'])
                response = {'ok': True}
            elif request['op'] == 'query' and engine is not None:
                response = {'query_id': request['query_id'], 'results': engine.search(request['vectors'])}
            else:
                raise ValueError('Expected load followed by queries')
        except Exception as exc:
            print(repr(exc), file=sys.stderr, flush=True)
            if request is not None and request.get('op') == 'query':
                response = {'query_id': request.get('query_id'), 'results': []}
            else:
                response = {'ok': False}
        sys.stdout.buffer.write(orjson.dumps(response)+b'\n')
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
