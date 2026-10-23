"""Trusted verifier; all test queries remain in this root-owned process."""
import csv
import errno
import json
from scoring_parameters import SCORING
import os
from pathlib import Path
import secrets
import signal
import time
import traceback
import numpy as np
from metrics import ndcg10, reward, valid_ranking
from oracle import Oracle, QueryFailure
from runtime import Worker, Violation, signal_members, writable_size, asset_size

PUBLIC = Path('/task/public')
PRIVATE = Path('/task/private/data')
LOGS = Path('/logs/verifier')
WORK = Path('/work')


def write(path, value):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)


def labels(path):
    out = {}
    with path.open() as stream:
        for r in csv.DictReader(stream, delimiter='\t'):
            out.setdefault(r['query-id'], {})[r['corpus-id']] = int(r['score'])
    return out


def verify_storage(fixed):
    config = json.loads((WORK/'.storage.json').read_text())
    capacity = ((64 << 30)-fixed-(512 << 20))//4096*4096
    fs = os.statvfs(WORK)
    if config['probe'] or config['fixed_bytes'] != fixed or config['image_capacity_bytes'] != capacity:
        raise RuntimeError('Storage volume does not match fixed assets')
    if os.stat(WORK).st_dev == os.stat('/').st_dev or fs.f_blocks*fs.f_frsize > capacity:
        raise RuntimeError('Bounded storage volume is absent or too large')
    if any(p.name not in ('.storage.json', 'lost+found') for p in WORK.iterdir()):
        raise RuntimeError('Verifier needs a fresh workspace')
    submission_bytes = writable_size('/app')
    if submission_bytes > capacity:
        raise Violation('aggregate storage exceeded by submission artifacts')
    reserve = WORK/'.submission-reserve'
    try:
        with reserve.open('xb') as stream:
            os.posix_fallocate(stream.fileno(), 0, max(4096, submission_bytes))
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise Violation('aggregate storage exhausted by submission artifacts') from exc
        raise
    reserve.chmod(0o600)
    runtime = WORK/'runtime'
    runtime.mkdir(mode=0o700)
    os.chown(runtime, 10001, 10001)
    return runtime


def main():
    verification_started = time.monotonic()
    LOGS.mkdir(parents=True, exist_ok=True)
    LOGS.chmod(0o700)
    (LOGS/'reward.txt').write_text('0\n')
    write(LOGS/'reward.json', {'reward':0.0})
    report = {'status': 'initializing', 'raw_reward': 0.0, 'score': 0.0,
              'judge': 'pending_integrity_audit', 'queries': []}
    worker = None
    try:
        config = json.loads((PUBLIC/'config.json').read_text())
        refs = SCORING
        if refs.get('test_queries') != 3452:
            raise RuntimeError('Invalid scoring query count')
        reward(0, refs['B'], refs['U'])
        if refs['U']-refs['B'] < refs['minimum_validated_gap'] or refs['minimum_validated_gap'] <= 0:
            raise RuntimeError('Invalid scoring reference gap')
        if config['documents'] != 250000 or config['cheap_dimension'] != 384 or config['expensive_dimension'] != 4096:
            raise RuntimeError('Unexpected reduced-corpus configuration')
        if config['score_budget'] != 20 or refs['budget'] != 20 or refs['documents'] != 250000:
            raise RuntimeError('Scoring budget or reference corpus mismatch')
        fixed = config['fixed_asset_bytes']
        # No input bytes may silently escape the 64 GiB accounting envelope.
        actual = asset_size(PUBLIC)+asset_size(PRIVATE)
        if fixed != actual: raise RuntimeError('Fixed asset sizes changed')
        if actual >= 5_000_000_000: raise RuntimeError('Fixed task assets must remain below 5 decimal GB')
        work = verify_storage(fixed)
        if not os.access('/app/search.sh', os.X_OK):
            raise Violation('Missing executable /app/search.sh')
        queries = [json.loads(line) for line in (PRIVATE/'queries.jsonl').read_text().splitlines()]
        qrels = labels(PRIVATE/'qrels.tsv')
        if len(queries) != 3452 or len({q['query_id'] for q in queries}) != 3452 or set(qrels) != {q['query_id'] for q in queries}:
            raise RuntimeError('Test query/qrels coverage mismatch')
        expensive = np.memmap(PRIVATE/'expensive.f32', dtype='<f4', mode='r', shape=(250000,4096))
        query_vectors = np.memmap(PRIVATE/'queries.f32', dtype='<f4', mode='r', shape=(3452,4096))
        oracle = Oracle(expensive, budget=config['score_budget'])
        cpus = sorted(os.sched_getaffinity(0))
        if len(cpus) != 16: raise RuntimeError('Verifier must be pinned to exactly 16 CPUs')
        cg = Path('/sys/fs/cgroup')
        if (cg/'memory.max').read_text().strip() != str(32 << 30):
            raise RuntimeError('Verifier requires a 32 GiB aggregate memory cgroup')
        def oom_count():
            return int(dict(line.split() for line in (cg/'memory.events').read_text().splitlines())['oom'])
        initial_oom = oom_count()
        signal_members(signal.SIGKILL)
        startup_total = 0
        peak_rss = peak_storage = 0

        def start(mode, number):
            nonlocal startup_total
            t0 = time.monotonic()
            deadline = t0+max(0,3600-startup_total)
            w = Worker(['/app/search.sh', '--data-dir', str(PUBLIC), '--index-dir', str(work/'index'),
                        '--mode', mode], str(work), LOGS/f'worker-{number}.stderr', cpus,
                       fixed_bytes=fixed+writable_size('/app'))
            try:
                if w.receive(deadline) != {'op':'ready'}: raise Violation('Expected ready after build/load')
                w.suspend()
                w.sample(force_disk=True, deadline=deadline)
                if startup_total+time.monotonic()-t0 > 3600: raise Violation('Build/load timeout')
                return w
            except BaseException as exc:
                w.close()
                if oom_count() != initial_oom:
                    raise Violation('aggregate memory exceeded during build/load') from exc
                raise
            finally:
                startup_total += time.monotonic()-t0

        worker = start('build', 0)
        if oom_count() != initial_oom: raise Violation('aggregate memory exceeded during build')
        for i, query in enumerate(queries):
            item = {'query_id': query['query_id'], 'ndcg10': 0.0, 'calls': 0, 'valid': False}
            if worker is None:
                worker = start('load', i+1)
                if oom_count() != initial_oom: raise Violation('aggregate memory exceeded during reload')
            token = secrets.token_hex(16)
            t0 = time.monotonic()
            deadline = t0+2.0
            oracle.begin(query_vectors[i], token, deadline)
            try:
                worker.resume()
                worker.send({'op':'query', 'token':token, 'text':query['text'], 'vector':query['vector']}, deadline)
                while True:
                    result = worker.receive(deadline)
                    if not isinstance(result, dict): raise QueryFailure('Expected object')
                    if result.get('op') == 'score':
                        worker.send(oracle.score(result), deadline)
                    elif set(result) == {'op','token','doc_ids'} and result['op']=='result' and result['token']==token:
                        if not valid_ranking(result['doc_ids'], len(expensive)):
                            raise QueryFailure('Invalid top-10 result')
                        worker.suspend()
                        worker.sample(force_disk=True, deadline=deadline)
                        elapsed = time.monotonic()-t0
                        if elapsed > 2.0: raise QueryFailure('Query timeout')
                        item.update(valid=True, ndcg10=ndcg10(result['doc_ids'], qrels[query['query_id']]),
                                    seconds=elapsed, doc_ids=result['doc_ids'])
                        break
                    else:
                        raise QueryFailure('Unexpected protocol response')
            except (QueryFailure, Violation) as exc:
                item.update(error=str(exc), seconds=time.monotonic()-t0)
                if isinstance(exc, Violation) and 'aggregate' in str(exc): raise
                peak_rss = max(peak_rss, worker.peak_rss)
                peak_storage = max(peak_storage, worker.peak_storage)
                worker.close()
                worker = None
            finally:
                item['calls'] = oracle.used
                oracle.close()
            if oom_count() != initial_oom: raise Violation('aggregate memory exceeded (cgroup OOM)')
            report['queries'].append(item)
            if worker:
                peak_rss = max(peak_rss, worker.peak_rss)
                peak_storage = max(peak_storage, worker.peak_storage)
            if (i+1)%50 == 0: write(LOGS/'progress.json', {'completed':i+1,'total':3452})
        quality = sum(q['ndcg10'] for q in report['queries'])/3452
        if oom_count() != initial_oom: raise Violation('aggregate memory exceeded')
        result = reward(quality, refs['B'], refs['U'])
        report.update(status='complete', Q=quality, B=refs['B'], U=refs['U'], raw_reward=result, score=100*result,
                      build_load_seconds=startup_total, peak_aggregate_rss_bytes=peak_rss,
                      peak_total_storage_bytes=peak_storage, index_bytes=writable_size(work/'index'))
        report['peak_cgroup_memory_bytes'] = int((cg/'memory.peak').read_text())
    except Violation as exc:
        report.update(status='submission_failure', error=str(exc))
    except Exception as exc:
        report.update(status='infrastructure_failure', error=str(exc), traceback=traceback.format_exc())
    finally:
        if worker: worker.close()
        signal_members(signal.SIGKILL)
        report['verification_seconds'] = time.monotonic()-verification_started
        if 'startup_total' in locals(): report.setdefault('build_load_seconds', startup_total)
        peak_file = Path('/sys/fs/cgroup/memory.peak')
        if peak_file.exists(): report['peak_cgroup_memory_bytes'] = int(peak_file.read_text())
        write(LOGS/'evaluation.json',report)
    return 1 if report['status']=='infrastructure_failure' else 0


if __name__=='__main__': raise SystemExit(main())
