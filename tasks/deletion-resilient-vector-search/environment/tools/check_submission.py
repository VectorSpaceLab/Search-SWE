#!/usr/bin/env python3
"""Small public quality/protocol check; does not replace full verifier resource gates."""
import argparse
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time

import faiss
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', default='/app/run.sh')
    ap.add_argument('--dataset', choices=['sift', 'gist'], default='sift')
    ap.add_argument('--queries', type=int, default=10)
    ap.add_argument('--stages', type=int, default=3)
    args = ap.parse_args()
    if not 1 <= args.stages <= 100:
        raise ValueError('stages must be 1..100')
    p = Path('/task/data/public') / args.dataset
    c = json.loads((p / 'config.json').read_text())
    d, n = c['dimension'], c['rows']
    if not 1 <= args.queries <= c['calibration_count']:
        raise ValueError(f"queries must be 1..{c['calibration_count']}; only the public examples are available")
    calibration = np.fromfile(p / 'calibration.f32', dtype='<f4').reshape(-1, d)
    if len(calibration) != c['calibration_count']:
        raise ValueError('Public example count does not match config.json')
    x = np.memmap(p / 'base.f32', dtype='<f4', mode='r', shape=(n, d))
    queries = calibration[:args.queries]
    deletes = np.fromfile(p / 'deletions.i32', dtype='<i4').reshape(100, 8000)
    faiss.omp_set_num_threads(1)
    faiss.cvar.distance_compute_blas_threshold = 2**30
    exact = faiss.IndexIDMap2(faiss.IndexFlatL2(d))
    exact.add_with_ids(x, np.arange(n, dtype=np.int64))
    with tempfile.TemporaryDirectory(prefix='deletion-check-', dir='/app') as work:
        environment = dict(os.environ, HOME=work, TMPDIR=work)
        process = subprocess.Popen([str(Path(args.run).resolve())], cwd=work, env=environment,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def request(obj, timeout):
            process.stdin.write(json.dumps(obj) + '\n')
            process.stdin.flush()
            if not selector.select(timeout):
                raise TimeoutError('Public self-check request timed out')
            return json.loads(process.stdout.readline())

        try:
            start = time.monotonic()
            result = request({'op': 'build', 'vectors': str(p / 'base.f32'), 'rows': n,
                              'dimension': d, 'work_dir': work, 'calibration': str(p / 'calibration.f32')}, 7200)
            if result.get('ok') is not True:
                raise ValueError('build response')
            print(json.dumps({'build_seconds': time.monotonic() - start}), flush=True)
            for stage in range(args.stages):
                ids = deletes[stage]
                result = request({'op': 'delete', 'stage': stage + 1, 'ids': ids.tolist()}, 1800)
                if result.get('ok') is not True:
                    raise ValueError('delete response')
                exact.remove_ids(ids.astype(np.int64))
                _, truth = exact.search(queries, 10)
                start = time.monotonic()
                outputs = [request({'op': 'query', 'query_id': i, 'vector': q.tolist()}, 1800) for i, q in enumerate(queries)]
                elapsed = time.monotonic() - start
                scores = []
                for i, result in enumerate(outputs):
                    values = result.get('results') if isinstance(result, dict) else None
                    valid = isinstance(values, list) and len(values) <= 10
                    valid = valid and type(result.get('query_id')) is int and result['query_id'] == i
                    if valid:
                        valid = all(isinstance(v, dict) and type(v.get('id')) is int
                                    and type(v.get('distance')) in [int, float]
                                    and math.isfinite(v['distance']) and v['distance'] >= 0 for v in values)
                    if not valid:
                        scores.append(0.)
                    else:
                        scores.append(len(set(v['id'] for v in values) & set(truth[i])) / 10)
                print(json.dumps({'stage': stage + 1, 'recall': float(np.mean(scores)), 'query_seconds': elapsed}), flush=True)
        finally:
            process.kill()
            process.wait()
            selector.close()


if __name__ == '__main__':
    main()
