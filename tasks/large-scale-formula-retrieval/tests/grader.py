"""Privileged scorer; submissions see one formula only after its clock starts."""
import json
import os
from pathlib import Path
import secrets
import time

import numpy as np
from development import check_development
from runtime import Worker, Violation
from scoring import read_qrels, evaluate
from repetition import (REPEATS, BUILD_TIMEOUT, LOAD_TIMEOUT, WARMUP_TIMEOUT,
                        QUERY_TIMEOUT, METRICS, median_result)
from storage import (evaluation_volume, file_bytes, prepare_serving_volume,
                     reset_serving_runtime, SERVING_LIMIT)

LOG = Path('/logs/verifier')
PUBLIC = Path('/task/data')
MAX_RESPONSE_LOG_CHARS = 64 << 10  # Five rounds fit within the diagnostic reserve.


def write(name, obj):
    (LOG / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def finish_report(report):
    events = Path('/sys/fs/cgroup/memory.events').read_text()
    report['cgroup_memory_events'] = events
    report['cgroup_memory_peak_bytes'] = int(Path('/sys/fs/cgroup/memory.peak').read_text())
    if any(int(r.split()[1]) for r in events.splitlines() if r.split()[0] in ['oom', 'oom_kill']):
        report['failure'] = 'memory limit'
    if report.get('failure'):
        report['raw_reward'] = 0.0
    report['raw_score'] = 100 * report['raw_reward']
    write('evaluation.json', report)


def main():
    started = time.monotonic()
    queries = [json.loads(s) for s in Path('/tests/data/queries.jsonl').read_text().splitlines()]
    labels = read_qrels(Path('/tests/data/qrels.tsv'))
    if len(queries) != 76 or set(labels) != {q['query_id'] for q in queries}:
        raise RuntimeError('Expected all 76 official test queries')
    mapping = np.load(PUBLIC / 'instance_visual.npy', mmap_mode='r')
    warmup = [json.loads(s) for s in (PUBLIC / 'validation/queries.jsonl').read_text().splitlines()][:3]
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 2:
        raise RuntimeError('Expected exactly 2 assigned CPUs')
    report = {'raw_reward': 0.0, 'raw_score': 0.0, 'queries': [], 'query_count': 76,
              'query_repeats': REPEATS,
              'judge': 'pending_integrity_audit', 'valid_measurement': True,
              'submission_bytes': file_bytes('/app'), 'public_bytes': file_bytes(PUBLIC)}
    report['development'], failure = check_development()
    if failure:
        report['failure'] = failure
        finish_report(report)
        return
    fixed = report['submission_bytes'] + report['public_bytes']
    if fixed > 64 << 30 or report['submission_bytes'] > os.statvfs('/work').f_bavail * 4096:
        report['failure'] = 'storage limit'
        finish_report(report)
        return
    if report['submission_bytes'] > SERVING_LIMIT:
        report['failure'] = 'serving footprint limit'
        finish_report(report)
        return
    worker = None
    count = 0
    peak = 0

    def new_worker(command, name):
        nonlocal count
        count += 1
        stage = Path('/work' if name == 'build' else '/serve')
        w = Worker(command, str(stage / 'runtime'), LOG / f'{name}-{count}.stderr', cpus, fixed,
                   allow_api=name == 'build')
        w.disk_root = stage
        return w

    def load_worker():
        reset_serving_runtime()
        w = new_worker(['/app/submission/serve.sh'], 'serve')
        try:
            w.begin(LOAD_TIMEOUT)
            response = w.request({'op': 'load', 'data_dir': str(PUBLIC), 'index_dir': '/serve/index',
                                  'work_dir': '/serve/runtime'})
            load = w.finish()
            if response != {'ok': True}:
                raise Violation('load must return {"ok":true}')
            w.begin(WARMUP_TIMEOUT)
            for i, q in enumerate(warmup):
                w.request({'op': 'query', 'query_id': f'warmup-{i}', 'latex': q['latex']})
            warm = w.finish()
            report.setdefault('loads', []).append({'load': load, 'warmup': warm})
            return w
        except BaseException:
            w.close()
            raise

    with evaluation_volume():
        try:
            for name in ['build.sh', 'serve.sh']:
                if not Path('/app/submission', name).is_file() or not os.access('/app/submission/' + name, os.X_OK):
                    raise Violation('Missing executable ' + name)
            Path('/work/index').mkdir()
            os.chown('/work/index', 10001, 10001)
            worker = new_worker(['/opt/conda/bin/python', '/task/tools/build_driver.py'], 'build')
            worker.begin(BUILD_TIMEOUT)
            response = worker.request({'command': ['/app/submission/build.sh', '--data-dir', str(PUBLIC),
                                                   '--index-dir', '/work/index']})
            report['build'] = worker.finish()
            if not isinstance(response, dict) or response.get('ok') is not True:
                raise Violation('build failed')
            peak = max(peak, worker.lifetime_peak)
            worker.close()
            worker = None
            report['index_bytes'] = file_bytes('/work/index')
            report['serving_volume'] = prepare_serving_volume()
            attempts = {q['query_id']: [] for q in queries}
            for repeat in range(REPEATS):
                # Build once; each pass loads the same index into a new process
                # with empty writable state and identical warmup/query order.
                worker = load_worker()
                responses = []
                for q in queries:
                    qid = secrets.token_hex(12)
                    result = {'repeat': repeat + 1, 'ndcg_prime': 0.0,
                              'map_prime': 0.0, 'p_prime_10': 0.0, 'valid': False}
                    try:
                        if worker is None:
                            worker = load_worker()
                        worker.begin(QUERY_TIMEOUT, query=True)
                        answer = worker.request({'op': 'query', 'query_id': qid, 'latex': q['latex']})
                        measurement = worker.finish()
                        result.update(evaluate(answer, qid, mapping, labels[q['query_id']]), **measurement)
                        raw = worker.last_response_text
                        responses.append({'query_id': q['query_id'],
                                          'response_json': raw[:MAX_RESPONSE_LOG_CHARS],
                                          'response_chars': len(raw),
                                          'response_truncated': len(raw) > MAX_RESPONSE_LOG_CHARS})
                        if not result['valid']:
                            peak = max(peak, worker.lifetime_peak)
                            worker.close()
                            worker = None
                    except (Violation, OSError, ValueError) as exc:
                        result['error'] = f'{type(exc).__name__}: {exc}'
                        if worker:
                            result['seconds'] = time.monotonic() - worker.phase_start
                            peak = max(peak, worker.lifetime_peak)
                            worker.close()
                            worker = None
                        if 'memory limit' in str(exc) or 'storage limit' in str(exc):
                            raise
                    attempts[q['query_id']].append(result)
                if worker:
                    peak = max(peak, worker.lifetime_peak)
                    worker.close()
                    worker = None
                # Flush each round instead of retaining five rounds of raw
                # responses in the memory-limited evaluator.
                write(f'responses-{repeat + 1}.json', responses)
                write('query-attempts.json', attempts)
            report['queries'] = [{'official_query_id': q['query_id'],
                                  **median_result(attempts[q['query_id']])} for q in queries]
        except (Violation, OSError, ValueError) as exc:
            report['failure'] = f'{type(exc).__name__}: {exc}'
        finally:
            if worker:
                peak = max(peak, worker.lifetime_peak)
                worker.close()
    for metric in METRICS:
        report[metric] = sum(q[metric] for q in report['queries']) / 76
    report.update(raw_reward=report['ndcg_prime'], lifetime_peak_rss_bytes=peak,
                  total_seconds=time.monotonic() - started)
    finish_report(report)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        write('infrastructure-error.json', {'error': f'{type(exc).__name__}: {exc}'})
        raise
