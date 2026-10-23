"""Privileged coordinator; hidden queries arrive individually after loading."""
import hashlib
import json
from runtime_limits import REFERENCE
import math
import os
import platform
from pathlib import Path
import time
import numpy as np
import faiss
import orjson
import psutil
from runtime import Worker, Violation
from scoring import recall, gated_reward, normalized_query_seconds
from storage import evaluation_volume, file_bytes
from development import check_development

LOG = Path('/logs/verifier')


def write(name, value):
    (LOG / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def current_baseline(queries, warm, truth, rows, public, cpus, ref):
    """Run only the pinned public baseline before any submitted code starts."""
    worker = None
    responses = []
    work = Path('/work/baseline')
    try:
        worker = Worker(['/task/tools/baseline/run.sh'], work, LOG / 'baseline.stderr',
                        cpus, file_bytes(public))
        worker.begin(ref['load_timeout_seconds'])
        answer = worker.request({'op': 'load', 'corpus': str(public / 'corpus'),
                                 'index': str(public / 'baseline'), 'work_dir': str(work)})
        measured = {'load': worker.finish()}
        if answer != {'ok': True}:
            raise RuntimeError('Pinned baseline failed loading')
        worker.begin(ref['warmup_timeout_seconds'])
        for i, q in enumerate(warm):
            worker.request({'op': 'query', 'query_id': i, 'vectors': q.tolist()})
        measured['warmup'] = worker.finish()
        worker.begin(ref['baseline_hard_timeout_seconds'], query=True)
        for i, q in enumerate(queries):
            responses.append(worker.request({'op': 'query', 'query_id': i, 'vectors': q.tolist()}))
        measured['query'] = worker.finish()
    except (Violation, BrokenPipeError, OSError, ValueError) as exc:
        raise RuntimeError('Pinned baseline measurement failed: ' + str(exc)) from exc
    finally:
        if worker:
            worker.close()
        # Baseline temporary data is verifier-private before submission starts.
        if work.exists():
            os.chown(work, 0, 0)
            work.chmod(0o700)
    measured['mean_recall_at_100'] = math.fsum(
        recall(answer, truth[i], rows, i) for i, answer in enumerate(responses)) / len(queries)
    if len(responses) != len(queries) or measured['mean_recall_at_100'] < ref['minimum_recall']:
        raise RuntimeError('Pinned baseline no longer meets the quality gate')
    return measured


def main():
    public = Path('/task/data/public')
    private = Path('/task/data/verifier')
    ref = REFERENCE
    if ref.get('status') != 'frozen' or ref.get('score_kind') != 'high_recall_relative_speed_v1':
        raise RuntimeError('Frozen high-recall speed anchors are required before grading')
    baseline_seconds = ref['baseline_query_seconds']
    reference_seconds = ref['reference_query_seconds']
    if (not all(math.isfinite(x) for x in [baseline_seconds, reference_seconds])
            or not 0 < reference_seconds < baseline_seconds or ref['minimum_recall'] != 0.99
            or not 0 < ref['query_hard_timeout_seconds'] <= 600
            or ref['baseline_hard_timeout_seconds'] != 600):
        raise RuntimeError('Invalid high-recall speed calibration')
    cpu = next(s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name'))
    if cpu != ref['cpu_model']:
        raise RuntimeError('Different CPU: recalibrate the full reference workload before evaluation')
    if np.__version__ != ref['numpy']:
        raise RuntimeError('Reference NumPy runtime changed; recalibrate before evaluation')
    versions = {'faiss': faiss.__version__, 'orjson': orjson.__version__, 'psutil': psutil.__version__}
    versions['python'] = platform.python_version()
    if versions != ref['runtime_versions']:
        raise RuntimeError('Reference search/protocol runtime changed; recalibrate before evaluation')
    if digest(Path('/tests/runtime.py')) != ref['supervisor_sha256']:
        raise RuntimeError('Reference protocol supervisor changed; recalibrate before evaluation')
    if digest(Path('/tests/test.sh')) != ref['verifier_entrypoint_sha256']:
        raise RuntimeError('Verifier setup changed; recalibrate before evaluation')
    for name, sha in ref['baseline_source_sha256'].items():
        if digest(Path('/task/tools') / name) != sha:
            raise RuntimeError('Frozen reference implementation changed: ' + name)
    for relative, sha in ref['input_sha256'].items():
        if digest(Path('/task/data') / relative) != sha:
            raise RuntimeError('Input hash mismatch: ' + relative)
    corpus_ids = json.loads((public / 'corpus/ids.json').read_text())
    row_by_id = {doc: i for i, doc in enumerate(corpus_ids)}
    queries = np.fromfile(private / 'test/vectors.f32', dtype='<f4').reshape(-1, 32, 128)
    truth = np.fromfile(private / 'test/truth.i32', dtype='<i4').reshape(-1, 100)
    warm = np.fromfile(public / 'dev/vectors.f32', dtype='<f4').reshape(-1, 32, 128)[:5]
    if len(queries) != 10000 or truth.shape != (10000, 100) or len(corpus_ids) != 522931:
        raise RuntimeError('Unexpected complete workload shape')
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 8:
        raise RuntimeError('This calibration requires exactly eight assigned CPU cores')
    responses = []
    report = {'raw_reward': 0.0, 'raw_score': 0.0, 'test_query_count': len(queries), 'completed_queries': 0,
              'baseline_query_seconds': baseline_seconds, 'reference_query_seconds': reference_seconds,
              'minimum_recall': ref['minimum_recall'], 'query_budget_seconds': ref['query_hard_timeout_seconds'],
              'submission_bytes': file_bytes('/app'), 'index_bytes': file_bytes('/app/index'),
              'judge': 'pending_integrity_audit', 'valid_measurement': True, 'resources_ok': True}
    report['development'], development_failure = check_development()
    if development_failure:
        report['failure'] = {'phase': 'development', 'error': development_failure}
        report['resources_ok'] = False
        write('evaluation.json', report)
        print(json.dumps(report), flush=True)
        return
    # Sparse/oversized transferred files must be a submission resource failure,
    # not an infrastructure error while reserving their disk footprint.
    fs = os.statvfs('/work')
    if (report['submission_bytes'] + file_bytes(public) > 32 << 30 or
            report['submission_bytes'] > fs.f_bavail * fs.f_frsize):
        report['failure'] = {'phase': 'artifacts', 'error': 'storage limit'}
        report['resources_ok'] = False
        write('evaluation.json', report)
        print(json.dumps(report), flush=True)
        return
    worker = None
    phase = 'load'
    with evaluation_volume():
        try:
            if not Path('/app/run.sh').is_file() or not os.access('/app/run.sh', os.X_OK):
                raise Violation('Missing executable /app/run.sh')
            report['current_baseline'] = current_baseline(
                queries, warm, truth, row_by_id, public, cpus, ref)
            write('current-baseline.json', report['current_baseline'])
            worker = Worker(['/app/run.sh'], '/work/runtime', LOG / 'submission.stderr', cpus,
                            file_bytes('/app') + file_bytes(public))
            worker.begin(ref['load_timeout_seconds'])
            answer = worker.request({'op': 'load', 'corpus': str(public / 'corpus'),
                                     'index': '/app/index', 'work_dir': '/work/runtime'})
            report['load'] = worker.finish()
            if answer != {'ok': True}:
                raise Violation('Load must respond {"ok":true}')
            phase = 'warmup'
            worker.begin(ref['warmup_timeout_seconds'])
            for i, q in enumerate(warm):
                worker.request({'op': 'query', 'query_id': i, 'vectors': q.tolist()})
            report['warmup'] = worker.finish()
            phase = 'query'
            worker.begin(report['query_budget_seconds'], query=True)
            for i, q in enumerate(queries):
                responses.append(worker.request({'op': 'query', 'query_id': i, 'vectors': q.tolist()}))
            report['query'] = worker.finish()
        except (Violation, BrokenPipeError, OSError, ValueError) as exc:
            report['failure'] = {'phase': phase, 'error': f'{type(exc).__name__}: {exc}'}
            report['resources_ok'] = False
            if worker and phase == 'query':
                report['query'] = {'seconds': time.monotonic() - worker.phase_start,
                                   'rss_bytes': worker.peak, 'storage_bytes': worker.disk_peak}
        finally:
            if worker:
                report['lifetime_peak_rss_bytes'] = worker.lifetime_peak
                worker.close()
    values = [recall(answer, truth[i], row_by_id, i) for i, answer in enumerate(responses)]
    report['completed_queries'] = len(responses)
    recall_sum = math.fsum(values)
    report['mean_recall_at_100'] = recall_sum / len(queries)
    report['quality_ok'] = round(report['mean_recall_at_100'], 12) >= ref['minimum_recall']
    report['workload_complete'] = len(responses) == len(queries)
    if 'query' in report:
        seconds = report['query']['seconds']
        current_seconds = report['current_baseline']['query']['seconds']
        report['normalized_query_seconds'] = normalized_query_seconds(
            seconds, baseline_seconds, current_seconds)
        report['raw_reward'] = round(gated_reward(recall_sum, len(queries), report['normalized_query_seconds'],
            baseline_seconds, reference_seconds,
            report['resources_ok'] and report['workload_complete'], ref['minimum_recall']), 12)
        report['speedup_over_baseline'] = current_seconds / seconds if seconds > 0 else None
        report['queries_per_second'] = len(responses) / seconds if seconds > 0 else None
    if not report['quality_ok'] and 'failure' not in report:
        report['failure'] = {'phase': 'quality', 'error': 'Mean Recall@100 is below 0.99'}
    report['raw_score'] = 100 * report['raw_reward']
    report['cgroup_memory_peak_bytes'] = int(Path('/sys/fs/cgroup/memory.peak').read_text())
    events = Path('/sys/fs/cgroup/memory.events').read_text()
    report['cgroup_memory_events'] = events
    if any(int(line.split()[1]) for line in events.splitlines() if line.split()[0] in ['oom', 'oom_kill']):
        report.update(raw_reward=0.0, raw_score=0.0, resources_ok=False)
    write('evaluation.json', report)
    print(json.dumps(report, allow_nan=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        write('infrastructure-error.json', {'error': f'{type(exc).__name__}: {exc}'})
        raise
