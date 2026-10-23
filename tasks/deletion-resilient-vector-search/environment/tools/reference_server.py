#!/usr/bin/env python3
"""Public fixed FAISS 1.15.0 references: exact full scan and HNSW tombstones.

--keep is only for author-side measurement of independently rebuilt live sets.
It does not authorize contestants to rebuild after each deletion.
"""
import argparse
import gc
import json
import sys

import faiss
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kind', choices=['full', 'hnsw'], required=True)
    ap.add_argument('--keep', help='author-side original row IDs for one rebuilt reference')
    args = ap.parse_args()
    index = None
    original = None
    alive = None
    edge_count = 0
    for line in sys.stdin:
        request = json.loads(line)
        op = request['op']
        if op == 'build':
            faiss.omp_set_num_threads(16)
            d, n = request['dimension'], request['rows']
            data = np.memmap(request['vectors'], dtype='<f4', mode='r', shape=(n, d))
            original = np.fromfile(args.keep, dtype='<i4') if args.keep else np.arange(n, dtype=np.int32)
            if args.kind == 'full':
                index = faiss.IndexIDMap2(faiss.IndexFlatL2(d))
            else:
                index = faiss.IndexHNSWFlat(d, 32)
                index.hnsw.efConstruction = 40
                index.hnsw.efSearch = 128
            for start in range(0, len(original), 8192):
                ids = original[start:start + 8192]
                block = np.ascontiguousarray(data[ids])
                if args.kind == 'full':
                    index.add_with_ids(block, ids.astype(np.int64))
                else:
                    index.add(block)
            del data, block, ids
            gc.collect()
            if args.kind == 'hnsw':
                edge_count = int(np.count_nonzero(faiss.vector_to_array(index.hnsw.neighbors) >= 0))
            alive = np.ones(n, dtype=np.uint8)
            bitmap_dirty = True
            response = {'ok': True, 'edge_count': edge_count}
        elif op == 'delete':
            faiss.omp_set_num_threads(16)
            ids = np.asarray(request['ids'], dtype=np.int64)
            alive[ids] = 0
            bitmap_dirty = True
            if args.kind == 'full':
                index.remove_ids(ids)
            response = {'ok': True, 'edge_count': edge_count}
        elif op == 'query':
            faiss.omp_set_num_threads(1)
            q = np.asarray([request['vector']], dtype=np.float32)
            if args.kind == 'hnsw':
                # Cache the bitmap by deletion count; refreshing it is query work.
                if bitmap_dirty:
                    bitmap = np.packbits(alive[original], bitorder='little')
                    selector = faiss.IDSelectorBitmap(len(bitmap), faiss.swig_ptr(bitmap))
                    bitmap_dirty = False
                params = faiss.SearchParametersHNSW()
                params.efSearch = 128
                params.sel = selector
                faiss.cvar.hnsw_stats.reset()
                distances, labels = index.search(q, 10, params=params)
                calls = int(faiss.cvar.hnsw_stats.ndis)
                labels = np.asarray([[int(original[i]) if i >= 0 else -1 for i in labels[0]]])
            else:
                distances, labels = index.search(q, 10)
                calls = int(index.ntotal)
            response = {'query_id': request['query_id'], 'results': [
                {'id': int(i), 'distance': float(v)} for i, v in zip(labels[0], distances[0]) if i >= 0
            ], 'distance_computations': calls}
        else:
            raise ValueError(f'Unknown operation {op}')
        print(json.dumps(response, separators=(',', ':'), allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
