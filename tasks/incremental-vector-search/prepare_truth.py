#!/usr/bin/env python3
"""Generate exhaustive float32 L2 targets for each live-corpus stage offline.

This is data preparation, not timing calibration. Query batching parallelizes
independent exact scans here; formal reference queries are single-threaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
from kernel import kernel_signature


def prepare(dim, data_root=ROOT / "data"):
    public, private = data_root / f"public/{dim}", data_root / f"private/{dim}"
    initial = np.load(public / "initial.npy", mmap_mode="r")
    inserts = np.load(private / "inserts.npy", mmap_mode="r")
    queries = np.load(private / "queries.npy", mmap_mode="r")
    if initial.shape != (105_000, dim) or inserts.shape != queries.shape or queries.shape != (10_000, dim):
        raise ValueError("Unexpected prepared data shapes")
    # Keep Faiss's direct distance kernel identical to the public reference.
    # Large-batch GEMM uses a different float32 rounding path and is not used.
    faiss.cvar.distance_compute_blas_threshold = 2_147_483_647
    faiss.omp_set_num_threads(16)
    index = faiss.IndexFlatL2(dim)
    index.add(initial)
    target = np.lib.format.open_memmap(private / "truth.npy", mode="w+", dtype="<i8", shape=(10_000, 1000))
    distances = np.lib.format.open_memmap(private / "truth_distances.npy", mode="w+", dtype="<f4", shape=(10_000, 1000))
    for stage in range(10):
        lo, hi = stage * 1000, (stage + 1) * 1000
        index.add(inserts[lo:hi])
        d, ids = index.search(np.asarray(queries[lo:hi]), 1000)
        distances[lo:hi], target[lo:hi] = d, ids
        target.flush()
        distances.flush()
        print(f"{dim}: exact targets stage {stage + 1}/10", flush=True)
    manifest = {"faiss_version": faiss.__version__, "kernel": "IndexFlatL2 direct float32",
                "runtime_signature": kernel_signature(),
                "threads": 16, "scope": "offline independent-query parallelism, not time calibration",
                "files": []}
    for path in (private / "truth.npy", private / "truth_distances.npy"):
        with path.open("rb") as stream:
            manifest["files"].append({"path": path.name, "size_bytes": path.stat().st_size,
                                     "sha256": hashlib.file_digest(stream, "sha256").hexdigest()})
    (private / "truth-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimension", type=int, nargs="+", choices=[1536, 3072], default=[1536, 3072])
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    for dimension in args.dimension:
        prepare(dimension, args.data_root)
