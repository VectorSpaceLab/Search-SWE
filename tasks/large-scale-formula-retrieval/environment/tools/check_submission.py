"""Public development checker. Final isolation and quotas belong to the verifier."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import tempfile

import numpy as np
from scoring import read_qrels, evaluate


SERVING_CAPACITY_BYTES = 40 << 20
ARTIFACT_LIMIT_BYTES = 34 << 20


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--submission', type=Path, default=Path('/app/submission'))
    ap.add_argument('--index-dir', type=Path, required=True)
    ap.add_argument('--data-dir', type=Path, default=Path('/task/data/public'))
    ap.add_argument('--skip-build', action='store_true')
    ap.add_argument('--output', type=Path)
    a = ap.parse_args()
    a.submission, a.index_dir, a.data_dir = a.submission.resolve(), a.index_dir.resolve(), a.data_dir.resolve()
    a.index_dir.mkdir(parents=True, exist_ok=True)
    build_runtime = a.index_dir.parent / (a.index_dir.name + '-build-runtime')
    build_runtime.mkdir(exist_ok=True)
    environment = dict(os.environ, TMPDIR=str(build_runtime), HOME=str(build_runtime))
    report = {'queries': [], 'scope': 'public diagnostics with prepared artifact limit; final physical quotas and isolation are not simulated',
              'artifact_limit_bytes': ARTIFACT_LIMIT_BYTES, 'serving_capacity_bytes': SERVING_CAPACITY_BYTES}
    if not a.skip_build:
        start = time.monotonic()
        subprocess.run([str(a.submission / 'build.sh'), '--data-dir', str(a.data_dir), '--index-dir', str(a.index_dir)],
                       env=environment, check=True, timeout=3600)
        report['build_seconds'] = time.monotonic() - start
    def allocated_bytes(root):
        total = 0
        seen = set()
        for p in root.rglob('*'):
            if p.is_file() and not p.is_symlink():
                s = p.stat()
                if (s.st_dev, s.st_ino) not in seen:
                    seen.add((s.st_dev, s.st_ino))
                    total += max(s.st_size, s.st_blocks * 512)
        return total
    report['submission_and_index_bytes'] = allocated_bytes(a.submission) + allocated_bytes(a.index_dir)
    if report['submission_and_index_bytes'] > ARTIFACT_LIMIT_BYTES:
        report.update(score=0, ndcg_prime=0, error='prepared artifact limit: submission/models and index exceed 34 MiB')
        payload = json.dumps(report, indent=2) + '\n'
        if a.output:
            a.output.write_text(payload)
        print(payload)
        return
    runtime = Path(tempfile.mkdtemp(prefix=a.index_dir.name + '-serve-', dir=a.index_dir.parent))
    environment.update(TMPDIR=str(runtime), HOME=str(runtime))
    labels = read_qrels(a.data_dir / 'dev/qrels.tsv')
    mapping = np.load(a.data_dir / 'instance_visual.npy', mmap_mode='r')
    queries = [json.loads(s) for s in (a.data_dir / 'dev/queries.jsonl').read_text().splitlines()]
    process = subprocess.Popen([str(a.submission / 'serve.sh')], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               env=environment, start_new_session=True)
    sel = selectors.DefaultSelector()
    sel.register(process.stdout, selectors.EVENT_READ)
    buffer = bytearray()

    def request(obj, timeout):
        nonlocal buffer
        start = time.monotonic()
        process.stdin.write((json.dumps(obj) + '\n').encode())
        process.stdin.flush()
        while b'\n' not in buffer:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0 or not sel.select(remaining):
                raise TimeoutError('response deadline')
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('service closed stdout')
            buffer.extend(chunk)
            if len(buffer) > 1 << 20:
                raise ValueError('response exceeds 1 MiB')
        line, _, tail = buffer.partition(b'\n')
        buffer = bytearray(tail)
        return json.loads(line), time.monotonic() - start

    try:
        response, report['load_seconds'] = request({'op': 'load', 'data_dir': str(a.data_dir),
                                                    'index_dir': str(a.index_dir), 'work_dir': str(runtime)}, 120)
        if response != {'ok': True}:
            raise ValueError('expected load acknowledgment')
        for q in queries[:3]:
            request({'op': 'query', **q}, 10)
        for q in queries:
            answer, seconds = request({'op': 'query', **q}, .05)
            result = evaluate(answer, q['query_id'], mapping, labels[q['query_id']])
            report['queries'].append({'query_id': q['query_id'], 'seconds': seconds, **result})
    except (TimeoutError, RuntimeError, ValueError, OSError) as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        sel.close()
    for name in ['ndcg_prime', 'map_prime', 'p_prime_10']:
        report[name] = sum(q[name] for q in report['queries']) / len(queries)
    report['score'] = 100 * report['ndcg_prime']
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if a.output:
        a.output.write_text(payload)
    print(payload)


if __name__ == '__main__':
    main()
