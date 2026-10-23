#!/usr/bin/env python3
"""Reconstruct exact live-set Top-10 answers from pinned prepared inputs.

The full-corpus exact Top-1024 is sufficient whenever at least ten of its
members survive a stage: all excluded corpus vectors are no nearer. This is
checked for every query/stage. Any insufficient candidate set is recomputed
against that complete live corpus, never padded with approximate answers.
The final bytes must match frozen hashes, including the reference's tie policy.
This program is author/restore-only and is never mounted in the agent.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import faiss
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--task-root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--dataset', choices=['sift', 'gist'], required=True)
    ap.add_argument('--threads', type=int, default=16)
    ap.add_argument('--verify-only', action='store_true')
    args = ap.parse_args()
    if faiss.__version__ != '1.15.0':
        raise RuntimeError('Restore with the pinned FAISS 1.15.0 runtime')
    public = args.task_root / 'data/public' / args.dataset
    private = args.task_root / 'data/verifier' / args.dataset
    sys.path.insert(0, str(args.task_root / 'tests'))
    from runtime_limits import REFERENCES
    ref = REFERENCES[args.dataset]
    config = json.loads((public / 'config.json').read_text())
    d, n = config['dimension'], config['rows']
    target = private / 'truth.i32'
    if not args.verify_only:
        faiss.omp_set_num_threads(args.threads)
        # Preserve the single-query direct-L2 arithmetic rather than BLAS x²+y²-2xy.
        faiss.cvar.distance_compute_blas_threshold = 2**30
        x = np.memmap(public / 'base.f32', dtype='<f4', mode='r', shape=(n, d))
        q = np.fromfile(private / 'queries.f32', dtype='<f4').reshape(-1, d)
        deletes = np.fromfile(private / 'deletions.i32', dtype='<i4').reshape(100, 8000)
        exact = faiss.IndexFlatL2(d)
        exact.add(x)
        nearest = np.empty((len(q), 1024), dtype=np.int64)
        for start in range(0, len(q), 64):
            _, nearest[start:start + 64] = exact.search(q[start:start + 64], 1024)
        alive = np.ones(n, dtype=bool)
        results = np.empty((100, len(q), 10), dtype='<i4')
        fallbacks = 0
        for stage, ids in enumerate(deletes):
            alive[ids] = False
            insufficient = []
            for i, candidates in enumerate(nearest):
                live = candidates[alive[candidates]]
                if len(live) < 10:
                    insufficient.append(i)
                else:
                    results[stage, i] = live[:10]
            if insufficient:
                ids = np.flatnonzero(alive)
                current = faiss.IndexFlatL2(d)
                current.add(np.asarray(x[ids]))
                _, local = current.search(q[insufficient], 10)
                results[stage, insufficient] = ids[local]
                fallbacks += len(insufficient)
            print(json.dumps({'dataset': args.dataset, 'stage': stage + 1, 'fallback_queries': len(insufficient)}), flush=True)
        temp = target.with_suffix('.tmp')
        # Recall is set-based. Canonical ID order makes byte hashes independent
        # of otherwise irrelevant tie/result ordering within the same Top-10 set.
        results.sort(axis=2)
        results.tofile(temp)
        temp.chmod(0o600)
        temp.replace(target)
        print(json.dumps({'full_live_fallbacks': fallbacks}), flush=True)
    with target.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    if ref and sha != ref['private_sha256']['truth.i32']:
        raise ValueError('Regenerated truth differs from frozen reference; do not evaluate')
    print(json.dumps({'path': str(target), 'sha256': sha, 'frozen_hash_verified': ref is not None}), flush=True)


if __name__ == '__main__':
    main()
