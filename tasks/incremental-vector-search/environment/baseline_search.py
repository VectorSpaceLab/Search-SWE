"""Optional public reference: full-corpus PQ4 scan with exact L2 reranking.

Each first timed query computes Top1000; later K requests reuse prefixes.
Every insertion updates both components of the logical index and clears queries.
"""
from contextlib import contextmanager
import ctypes
import orjson as json
import os
import sys

# Released query CPUs must not be occupied by idle construction thread pools.
os.environ["KMP_BLOCKTIME"] = "0"
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"

import faiss
import numpy as np
from threadpoolctl import threadpool_limits


query_blas = threadpool_limits(limits=1, user_api="blas")
mkl = ctypes.CDLL(os.path.join(sys.prefix, "lib", "libmkl_intel_lp64.so.2"),
                  mode=os.RTLD_NOLOAD | os.RTLD_LOCAL)
mkl.MKL_Set_Num_Threads_Local.argtypes = [ctypes.c_int]
mkl.MKL_Set_Num_Threads_Local.restype = ctypes.c_int
mkl.MKL_Get_Max_Threads.argtypes = []
mkl.MKL_Get_Max_Threads.restype = ctypes.c_int


def set_mkl_threads(count):
    mkl.MKL_Set_Num_Threads_Local(count)
    if mkl.MKL_Get_Max_Threads() != count:
        raise RuntimeError("MKL thread limit did not apply")


@contextmanager
def parallel_blas(threads):
    with threadpool_limits(limits=threads, user_api="blas"):
        set_mkl_threads(threads)
        try:
            yield
        finally:
            set_mkl_threads(1)


set_mkl_threads(1)
index = None
base_index = None
quantized_index = None
cache = {}
for line in sys.stdin.buffer:
    request = json.loads(line)
    if request["op"] == "build":
        threads = request.get("threads", 16)
        faiss.omp_set_num_threads(threads)
        vectors = np.load(request["vectors"], mmap_mode="r", allow_pickle=False)
        dimension = vectors.shape[1]
        subquantizers = {1536: 128, 3072: 384}.get(dimension)
        if subquantizers is None:
            subquantizers = max(m for m in range(2, max(2, dimension // 8) + 1, 2)
                                if dimension % m == 0)
        quantized_index = faiss.IndexPQFastScan(dimension, subquantizers, 4)
        quantized_index.pq.cp.niter = 20
        quantized_index.pq.cp.seed = 17
        base_index = quantized_index
        index = faiss.IndexRefineFlat(base_index)
        index.k_factor = {1536: 1, 3072: 2}.get(dimension, 3)
        rng = np.random.Generator(np.random.PCG64(17))
        rows = rng.choice(len(vectors), min(262_144, len(vectors)), replace=False)
        with parallel_blas(threads):
            index.train(np.ascontiguousarray(vectors[rows]))
            index.add(vectors)
        faiss.cvar.distance_compute_blas_threshold = 2_147_483_647
        cache.clear()
        faiss.omp_set_num_threads(1)
        response = {"ok": True}
    elif request["op"] == "insert":
        threads = request.get("threads", 16)
        faiss.omp_set_num_threads(threads)
        with parallel_blas(threads):
            index.add(np.load(request["vectors"], allow_pickle=False))
        cache.clear()
        faiss.omp_set_num_threads(1)
        response = {"ok": True}
    else:
        faiss.omp_set_num_threads(1)
        query = np.asarray(request["vector"], dtype=np.float32)[None, :]
        key = query.tobytes()
        if key not in cache:
            set_mkl_threads(1)
            distances, ids = index.search(query, min(1000, index.ntotal))
            valid = (ids[0] >= 0) & np.isfinite(distances[0])
            cache[key] = ids[0][valid], np.sqrt(np.maximum(distances[0][valid], 0))
        ids, distances = cache[key]
        k = request["k"]
        response = {"ids": ids[:k].tolist(), "distances": distances[:k].tolist()}
    sys.stdout.buffer.write(json.dumps(response) + b"\n")
    sys.stdout.buffer.flush()
