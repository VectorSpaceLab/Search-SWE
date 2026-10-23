#!/usr/bin/env python3
"""Public exact L2 reference; persistent JSONL protocol, no query-result cache."""
import json
import os
import sys

import faiss
import numpy as np

faiss.cvar.distance_compute_blas_threshold = 2_147_483_647
index = None
for line in sys.stdin:
    request = json.loads(line)
    op = request["op"]
    if op == "build":
        faiss.omp_set_num_threads(16)
        vectors = np.load(request["vectors"], mmap_mode="r", allow_pickle=False)
        index = faiss.IndexFlatL2(vectors.shape[1])
        index.add(vectors)
        response = {"ok": True}
    elif op == "insert":
        faiss.omp_set_num_threads(16)
        index.add(np.load(request["vectors"], allow_pickle=False))
        response = {"ok": True}
    elif op == "search":
        faiss.omp_set_num_threads(1)
        q = np.asarray(request["vector"], dtype=np.float32)[None, :]
        squared, ids = index.search(q, request["k"])
        response = {"ids": ids[0].tolist(), "distances": np.sqrt(np.maximum(squared[0], 0)).tolist()}
    else:
        raise ValueError(f"Unknown operation {op}")
    print(json.dumps(response, allow_nan=False, separators=(",", ":")), flush=True)
