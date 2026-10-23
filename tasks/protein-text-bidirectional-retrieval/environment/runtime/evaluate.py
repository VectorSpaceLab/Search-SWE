"""Separate trusted supervisor; never imports submitted Python in the scorer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time

import pynvml
from isolation import UID, cleanup
from metrics import paired_quality, paired_top1, score, summarize
from ranker import Ranker
from submission_transfer import SUBMISSION_BYTES


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def snapshot():
    root = Path('/app/submission')
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Missing submission directory')
    result = {}
    total = 0
    for p in [root, *root.rglob('*')]:
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError('Submission must contain only regular files and directories')
        os.chown(p, 0, 0)
        p.chmod(0o555 if p.is_dir() else 0o444)
        if p.is_file():
            total += p.stat().st_size
            if total > SUBMISSION_BYTES:
                raise ValueError('submission exceeds 256 KiB total logical bytes')
            with p.open('rb') as handle:
                result[str(p.relative_to(root))] = hashlib.file_digest(handle, 'sha256').hexdigest()
    if 'encoder.py' not in result:
        raise ValueError('Missing encoder.py')
    return result


class ResourceViolation(RuntimeError):
    pass


class Resources:
    def __init__(self):
        pynvml.nvmlInit()
        if pynvml.nvmlDeviceGetCount() != 1:
            raise ResourceViolation('Exactly one mapped GPU required')
        self.gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(self.gpu)
        if 'A100' not in name or not (39 << 30) <= pynvml.nvmlDeviceGetMemoryInfo(self.gpu).total <= (41 << 30):
            raise ResourceViolation('A100 40GB required')
        self.peak_gpu = self.peak_storage = 0
        self.last_disk = 0
        self.fixed = sum(p.stat().st_size for root in ['/task/models', '/task/public', '/task/private']
                         for p in Path(root).rglob('*') if p.is_file())

    def check(self):
        used = pynvml.nvmlDeviceGetMemoryInfo(self.gpu).used
        self.peak_gpu = max(self.peak_gpu, used)
        if time.monotonic() - self.last_disk >= 1:
            self.last_disk = time.monotonic()
            used = self.fixed + sum(p.stat().st_size for root in ['/app', '/tmp', '/dev/shm']
                                    for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink())
            self.peak_storage = max(self.peak_storage, used)
            if used > 100 << 30:
                raise ResourceViolation('100 GiB total task storage exceeded')

    def report(self):
        result = {'gpu': pynvml.nvmlDeviceGetName(self.gpu), 'gpu_uuid': pynvml.nvmlDeviceGetUUID(self.gpu),
                  'peak_gpu_bytes': self.peak_gpu, 'peak_task_storage_bytes': self.peak_storage}
        for path in ['/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/memory/memory.max_usage_in_bytes']:
            if Path(path).is_file():
                result['container_memory_peak_bytes'] = int(Path(path).read_text().strip())
                break
        result['visible_gpu_count'] = pynvml.nvmlDeviceGetCount()
        result['actual_cgroup_limits'] = {
            name: (Path('/sys/fs/cgroup') / name).read_text().strip()
            for name in ['cpu.max', 'memory.max', 'memory.swap.max', 'pids.max']
            if (Path('/sys/fs/cgroup') / name).is_file()
        }
        runtime = ['/task/runtime/' + name for name in
                   ['worker.py', 'isolation.py', 'metrics.py', 'submission_transfer.py', 'evaluate.py', 'ranker.py']]
        docs = ['/task/docs/' + name for name in
                ['environment.md', 'available_resources.md']]
        tests = ['/tests/' + name for name in
                 ['test_boundary.py', 'finalize.py', 'rewardkit_deepseek.py', 'test_finalizer.py', 'test.sh',
                  'test_metrics.py', 'test_transfer.py', 'test_runtime_gpu.py', 'test_ranker.py', 'grade.py', 'Dockerfile',
                  'docker-compose.yaml', 'jailbreak_judge/judge.toml']]
        result['trusted_phase_file_hashes'] = {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in runtime + docs + tests if Path(name).is_file()
        }
        return result


class Worker:
    def __init__(self, group, output, resources, phase):
        cleanup()
        self.work = Path(tempfile.mkdtemp(prefix='retrieval-', dir='/app'))
        self.work.chmod(0o700)
        if phase == 'candidates':
            with (self.work / 'candidates.jsonl').open('w') as handle:
                for row in read(group['candidate_file']):
                    handle.write(json.dumps({'value': row['value']}) + '\n')
            (self.work / 'candidates.jsonl').chmod(0o444)
        os.chown(self.work, UID, UID)
        self.log = (output / (group['key'] + '-' + phase + '-stderr.log')).open('ab')
        self.response_limit = (32 << 20) if phase == 'candidates' else (64 << 10)
        env = {k: os.environ[k] for k in ['PATH', 'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES',
                                         'NVIDIA_DRIVER_CAPABILITIES'] if k in os.environ}
        env.update(HOME=str(self.work), TMPDIR=str(self.work), RETRIEVAL_WORK_DIR=str(self.work),
                   XDG_CACHE_HOME=str(self.work / 'cache'), HF_HOME=str(self.work / 'hf'),
                   OMP_NUM_THREADS='16', OPENBLAS_NUM_THREADS='16', MKL_NUM_THREADS='16',
                   TOKENIZERS_PARALLELISM='false', PYTHONUNBUFFERED='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        self.p = subprocess.Popen(['/opt/conda/bin/python', '/task/runtime/worker.py'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self.log, env=env, bufsize=0)
        os.set_blocking(self.p.stdin.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.p.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.resources = resources

    def receive(self, deadline):
        while b'\n' not in self.buffer:
            self.resources.check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Request exceeded deadline')
            if self.selector.select(min(.02, remaining)):
                block = os.read(self.p.stdout.fileno(), 65536)
                if not block:
                    raise RuntimeError('Worker exited')
                self.buffer += block
                if len(self.buffer) > self.response_limit:
                    raise ValueError('Response exceeds phase byte limit')
        line, self.buffer = self.buffer.split(b'\n', 1)
        if self.buffer:
            raise RuntimeError('Unsolicited worker output')
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError('Worker response must be a JSON object')
        return response

    def call(self, message, deadline):
        payload = memoryview((json.dumps(message, separators=(',', ':')) + '\n').encode())
        while payload:
            self.resources.check()
            if time.monotonic() >= deadline:
                raise TimeoutError('Worker input deadline')
            try:
                n = os.write(self.p.stdin.fileno(), payload)
                payload = payload[n:]
            except BlockingIOError:
                time.sleep(.001)
        return self.receive(deadline)

    def close(self):
        cleanup()
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait(timeout=10)
        self.selector.close()
        self.p.stdin.close(); self.p.stdout.close(); self.log.close()
        shutil.rmtree(self.work)


def make_groups(root):
    groups = []
    for dataset in ['swissprot', 'proteinkg25']:
        for direction, query_modality, candidate_modality in [('p2t', 'protein', 'text'), ('t2p', 'text', 'protein')]:
            base = Path(root) / dataset
            groups.append({'key': dataset + '-' + direction, 'dataset': dataset, 'direction': direction,
                           'query_modality': query_modality, 'candidate_modality': candidate_modality,
                           'candidate_file': base / (candidate_modality + '.jsonl'),
                           'query_file': base / (query_modality + '.jsonl'), 'pairs_file': base / 'pairs.json'})
    return groups


def load_group(group, expected_queries):
    candidate_rows = read(group['candidate_file'])
    query_rows = read(group['query_file'])
    candidates = {r['id'] for r in candidate_rows}
    all_queries = {r['id'] for r in query_rows}
    pairs = json.loads(group['pairs_file'].read_text())
    expected = pairs[group['direction']]
    reverse = pairs['t2p' if group['direction'] == 'p2t' else 'p2t']
    if (len(candidate_rows) != 10000 or len(candidates) != 10000 or
            len(query_rows) != 10000 or len(all_queries) != 10000 or
            len(expected) != expected_queries or len(reverse) != expected_queries or
            not set(expected) <= all_queries or not set(expected.values()) <= candidates or
            any(reverse.get(v) != k for k, v in expected.items())):
        raise ValueError('Invalid candidate pools or paired query subset')
    return candidates, [q for q in query_rows if q['id'] in expected], expected


def evaluate(root, output, full_queries=False):
    evaluation_started = time.monotonic()
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    original = snapshot()
    resources = Resources()
    reports = []; paired_records = {}; pair_mappings = {}
    for group in make_groups(root):
        group_started = time.monotonic()
        expected_queries = 10000 if full_queries else 10
        candidates, queries, expected = load_group(group, expected_queries)
        records = []; worker = None; preparation = 0.0; ranker = None

        def prepare():
            nonlocal worker, preparation, ranker
            start = time.monotonic()
            try:
                deadline = start + 900.0 - preparation
                if ranker is None:
                    candidate_worker = Worker(group, output, resources, 'candidates')
                    try:
                        ready = candidate_worker.call({'phase': 'candidates', 'modality': group['candidate_modality']}, deadline)
                        if ready.get('ready') is not True or 'vectors' not in ready:
                            raise ValueError('Candidate encoding failed')
                        rows = read(group['candidate_file'])
                        ranker = Ranker([r['id'] for r in rows], ready['vectors'])
                    finally:
                        candidate_worker.close()
                worker = Worker(group, output, resources, 'queries')
                ready = worker.call({'phase': 'queries', 'modality': group['query_modality']}, deadline)
                if ready != {'ready': True}:
                    raise ValueError('Worker initialization failed')
                public = read(Path('/task/public/valid') / group['dataset'] / (group['query_modality'] + '.jsonl'))
                for sample in public[:3]:
                    response = worker.call({'query': sample['value']}, deadline)
                    if 'vector' not in response:
                        raise ValueError('Public warmup did not return a vector')
                    ranker.search(response['vector'])
            finally:
                preparation += time.monotonic() - start
            if preparation > 900:
                raise TimeoutError('Group candidate preparation exceeded 900 seconds')

        try:
            prepare()
            print(json.dumps({'group': group['key'], 'phase': 'online', 'prepare_seconds': preparation}), flush=True)
            for query in queries:
                row = {'query_id': query['id'], 'valid': False, 'hit20': False, 'hit1': False, 'timeout': False}
                started = time.monotonic()
                try:
                    response = worker.call({'query': query['value']}, started + 3.0)
                    ids = None
                    if 'vector' in response:
                        try:
                            ids = ranker.search(response['vector'])
                        except (ValueError, TypeError) as exc:
                            response = {'error': str(exc)}
                    elapsed = time.monotonic() - started
                    if elapsed > 3.0:
                        raise TimeoutError('Full query response exceeded 3 seconds')
                    row.update(valid=ids is not None, seconds=elapsed)
                    if row['valid']:
                        target = expected[query['id']]
                        row.update(hit20=target in ids, hit1=bool(ids and ids[0] == target))
                    else:
                        row['error'] = response.get('error', 'Missing query vector')
                except ResourceViolation:
                    raise
                except (TimeoutError, RuntimeError, BrokenPipeError, ValueError) as exc:
                    row.update(seconds=time.monotonic() - started, timeout=isinstance(exc, TimeoutError), error=str(exc))
                    cleanup_started = time.monotonic()
                    worker.close(); worker = None
                    row['cleanup_seconds'] = time.monotonic() - cleanup_started
                    row['actual_total_seconds'] = time.monotonic() - started
                records.append(row)
                if len(records) % 1000 == 0:
                    print(json.dumps({'group': group['key'], 'queries_completed': len(records),
                                      'group_wall_seconds': time.monotonic() - group_started}), flush=True)
                if not row['valid']:
                    row['statistical_seconds'] = 3.0
                if worker is None and len(records) < len(queries):
                    prepare()
            report = summarize(records)
            report.update(key=group['key'], prepare_seconds=preparation)
            reports.append(report)
            paired_records[group['key']] = records
            if group['direction'] == 'p2t':
                pair_mappings[group['dataset']] = expected
            dump(output / (group['key'] + '-queries.json'), records)
        finally:
            cleanup_started = time.monotonic()
            if worker is not None:
                worker.close()
            if reports and reports[-1]['key'] == group['key']:
                reports[-1]['cleanup_seconds'] = time.monotonic() - cleanup_started + sum(r.get('cleanup_seconds', 0.) for r in records)
                reports[-1]['total_seconds'] = time.monotonic() - group_started
    if snapshot() != original:
        raise ResourceViolation('Frozen submission was changed')
    datasets = []
    for dataset in ['swissprot', 'proteinkg25']:
        paired = paired_top1(pair_mappings[dataset], paired_records[dataset + '-p2t'], paired_records[dataset + '-t2p'])
        datasets.append(dict(dataset=dataset, **paired))
    result = {'valid': True, 'Q': paired_quality(datasets), 'datasets': datasets,
              'mean_recall_at_20': sum(g['recall_at_20'] for g in reports) / 4,
              'mean_accuracy_at_1': sum(g['accuracy_at_1'] for g in reports) / 4,
              'groups': reports, 'all_latency_gates': all(g['latency_gate'] for g in reports),
              'total_seconds': time.monotonic() - evaluation_started,
              'resources': resources.report(), 'submission_hashes': original}
    result['reward'] = score(reports, datasets)
    result['score'] = result['reward'] * 100
    dump(output / 'report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/task/public/valid')
    parser.add_argument('--output', required=True)
    parser.add_argument('--full', action='store_true', help='Require10000 labeled queries per group; private author/verifier use only')
    args = parser.parse_args()
    try:
        result = evaluate(args.root, args.output, full_queries=args.full)
        print(json.dumps(result))
    except Exception as exc:
        cleanup()
        Path(args.output).mkdir(parents=True, exist_ok=True)
        dump(Path(args.output) / 'report.json', {'valid': False, 'reward': 0.0, 'error': type(exc).__name__ + ': ' + str(exc)})
        raise


if __name__ == '__main__':
    main()
