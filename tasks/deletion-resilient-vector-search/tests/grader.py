#!/usr/bin/env python3
"""Evaluate the fixed 100-stage deletion workload in a separate verifier."""
import hashlib
import json
from runtime_limits import REFERENCES
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import faiss

from runtime import Worker, Violation
from scoring import recall, dataset_score, validate_reference
from storage import evaluation_volume, file_bytes

ROOT = Path('/logs/verifier')


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def evaluate(name, cpus):
    public = Path('/task/data/public') / name
    private = Path('/task/data/verifier') / name
    cfg = json.loads((public / 'config.json').read_text())
    ref = REFERENCES[name]
    validate_reference(ref)
    if ref['config'] != cfg:
        raise RuntimeError('Reference/input version mismatch')
    cpu_model = next(s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name'))
    if cpu_model != ref['hardware']['cpu_model'] or faiss.__version__ != ref['runtime']['faiss']:
        raise RuntimeError('Frozen timings require the documented calibration CPU and FAISS runtime; recalibrate before using another platform')
    d, n = cfg['dimension'], cfg['rows']
    q = np.fromfile(private / 'queries.f32', dtype='<f4').reshape(-1, d)
    calibration = np.fromfile(public / 'calibration.f32', dtype='<f4').reshape(-1, d)
    deletes = np.fromfile(private / 'deletions.i32', dtype='<i4').reshape(100, 8000)
    truth = np.fromfile(private / 'truth.i32', dtype='<i4').reshape(100, len(q), 10)
    if len(q) != cfg['test_query_count'] or len(np.unique(deletes)) != 800_000:
        raise RuntimeError('Invalid fixed workload')
    if (public / 'base.f32').stat().st_size != n * d * 4:
        raise RuntimeError('Invalid corpus bytes')
    for filename, expected in ref['private_sha256'].items():
        with (private / filename).open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
                raise RuntimeError('Hidden input integrity failure')
    for filename, expected in ref['public_sha256'].items():
        with (public / filename).open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
                raise RuntimeError('Public input integrity failure')
    command = ['/app/run.sh']
    if not Path(command[0]).is_file() or not os.access(command[0], os.X_OK):
        return {'valid': False, 'reward': 0.0, 'error': 'Missing executable /app/run.sh', 'stages': []}
    work = Path('/work') / name
    if work.exists():
        shutil.rmtree(work)
    fixed_bytes = file_bytes('/task/data/public') + file_bytes('/app')
    worker = None
    report = {'valid': False, 'reward': 0.0, 'stages': [], 'dataset': name}
    context = {'phase': 'build', 'stage': 0, 'budget_seconds': ref['build_timeout_seconds']}
    try:
        worker = Worker(command, work, ROOT / f'{name}.stderr', cpus, fixed_bytes)
        worker.begin(ref['build_timeout_seconds'])
        answer = worker.request({'op': 'build', 'vectors': str(public / 'base.f32'),
                                 'rows': n, 'dimension': d, 'work_dir': str(work),
                                 'calibration': str(public / 'calibration.f32')})
        report['build'] = worker.finish()
        if not isinstance(answer, dict) or answer.get('ok') is not True:
            raise Violation('Build did not return {"ok":true}')
        context = {'phase': 'public_calibration', 'stage': 0, 'budget_seconds': ref['calibration_timeout_seconds']}
        worker.begin(ref['calibration_timeout_seconds'], query=True)
        for i, vector in enumerate(calibration):
            worker.request({'op': 'query', 'query_id': i, 'vector': vector.tolist()})
        report['initial_calibration'] = worker.finish()
        live = np.ones(n, dtype=bool)
        for stage in range(100):
            ids = deletes[stage]
            context = {'phase': 'delete', 'stage': stage + 1, 'budget_seconds': ref['delete_timeout_seconds']}
            worker.begin(ref['delete_timeout_seconds'])
            answer = worker.request({'op': 'delete', 'stage': stage + 1, 'ids': ids.tolist()})
            deletion = worker.finish()
            if not isinstance(answer, dict) or answer.get('ok') is not True:
                raise Violation(f'Deletion {stage + 1} failed')
            edges = answer.get('edge_count')
            live[ids] = False
            budget = ref['full_scan_seconds'][stage] * .2
            context = {'phase': 'query', 'stage': stage + 1, 'budget_seconds': budget}
            worker.begin(budget, query=True)
            responses = [worker.request({'op': 'query', 'query_id': i, 'vector': vector.tolist()}) for i, vector in enumerate(q)]
            measured = worker.finish()
            r = sum(recall(res, truth[stage, i], live, i) for i, res in enumerate(responses)) / len(q)
            counters = [x.get('distance_computations') if isinstance(x, dict) else None for x in responses]
            counters_valid = all(type(c) is int and c >= 0 for c in counters)
            item = {'stage': stage + 1, 'live_rows': int(live.sum()), 'recall': r,
                    'delete_seconds': deletion['seconds'], 'delete_peak_rss_bytes': deletion['rss_bytes'],
                    'query_seconds': measured['seconds'], 'query_budget_seconds': budget,
                    'speedup': ref['full_scan_seconds'][stage] / measured['seconds'],
                    'rss_bytes': measured['rss_bytes'], 'storage_bytes': measured['storage_bytes'],
                    'reported_edge_count': edges if type(edges) is int and edges >= 0 else None,
                    'reported_distance_computations': sum(counters) if counters_valid else None}
            report['stages'].append(item)
            write(ROOT / f'{name}.json', report)
        report.update(dataset_score(report['stages'], report['initial_calibration']['rss_bytes'], ref))
        report['valid'] = True
        report['cumulative_delete_seconds'] = sum(s['delete_seconds'] for s in report['stages'])
        report['lifetime_peak_rss_bytes'] = worker.lifetime_peak
    except (Violation, BrokenPipeError, OSError, ValueError) as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['failure_context'] = context | {
            'elapsed_seconds': time.monotonic() - worker.phase_start if worker else None,
            'observed_peak_rss_bytes': worker.peak if worker else None,
            'observed_storage_bytes': worker.disk_peak if worker else None}
        report['reward'] = 0.0
    finally:
        if worker:
            worker.close()
        if work.exists():
            shutil.rmtree(work)
    write(ROOT / f'{name}.json', report)
    return report


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'reward.txt').write_text('0\n')
    write(ROOT / 'reward.json', {'reward': 0.0})
    # A missing calibration is an infrastructure error, never a memory-efficiency bonus.
    cpus = sorted(os.sched_getaffinity(0))[:16]
    if len(cpus) < 16:
        raise RuntimeError('This task requires 16 available logical CPUs')
    outputs = {}
    with evaluation_volume() as volume:
        write(ROOT / 'storage.json', {'image_capacity_bytes': volume.size,
                                     'available_bytes': os.statvfs('/work').f_bavail * os.statvfs('/work').f_frsize,
                                     'limit_bytes': 100 << 30})
        for name in ['sift', 'gist']:
            outputs[name] = evaluate(name, cpus)
    reward = sum(r['reward'] for r in outputs.values()) / 2
    write(ROOT / 'evaluation.json', {'deterministic_reward': reward, 'datasets': outputs})
    from report import export_curves
    export_curves(outputs, ROOT)
    # The integrity audit must succeed before test.sh finalizes a positive reward.
    print(json.dumps({'deterministic_reward': reward}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        ROOT.mkdir(parents=True, exist_ok=True)
        write(ROOT / 'infrastructure-error.json', {'error': f'{type(exc).__name__}: {exc}'})
        raise
