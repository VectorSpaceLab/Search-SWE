"""Public development runner and trusted separate-verifier execution engine."""
import argparse
import gzip
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

import isolation
from metrics import ndcg, validate_result
from model import BUDGET, MODEL, GPU_LIMIT, deployment_config, verify_model

LOCAL_SECONDS = 1.0
INFERENCE_SECONDS = 90.0
DEPLOY_SECONDS = 600.0
WARMUP_SECONDS = 60.0
STORAGE_LIMIT = 40 << 30
MAX_LINE = 256 << 10


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


class JsonPipe:
    def __init__(self, process, stderr_log=None):
        self.process = process
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
        os.set_blocking(process.stdout.fileno(), False)
        self.stderr_log = stderr_log
        self.stderr_bytes = 0
        if stderr_log is not None:
            os.set_blocking(process.stderr.fileno(), False)
            self.selector.register(process.stderr, selectors.EVENT_READ, 'stderr')

    def read(self, deadline, check=lambda: None):
        while True:
            check()
            if b'\n' in self.buffer:
                line, rest = self.buffer.split(b'\n', 1)
                if len(line)+1 > MAX_LINE:
                    raise ValueError('Protocol line exceeds 256 KiB')
                self.buffer = bytearray(rest)
                return json.loads(line)
            if len(self.buffer) > MAX_LINE:
                raise ValueError('Protocol line exceeds 256 KiB')
            if time.monotonic() >= deadline:
                raise TimeoutError('Response deadline exceeded')
            for key, _ in self.selector.select(min(.005, max(0, deadline-time.monotonic()))):
                data = os.read(key.fileobj.fileno(), 65536)
                if key.data == 'stderr':
                    if not data:
                        self.selector.unregister(key.fileobj)
                    else:
                        self.stderr_bytes += len(data)
                        if self.stderr_bytes > 1 << 20:
                            raise ValueError('Strategy stderr exceeds 1 MiB per query')
                        self.stderr_log.write(data)
                    continue
                if not data:
                    raise RuntimeError('Process exited without a complete JSON line')
                self.buffer.extend(data)

    def send(self, message):
        data = (json.dumps(message, separators=(',', ':')) + '\n').encode()
        if len(data) > MAX_LINE:
            raise ValueError('Protocol input exceeds 256 KiB')
        # Inputs can exceed a pipe's buffer. Bound writes while the receiver reads.
        fd = self.process.stdin.fileno()
        os.set_blocking(fd, False)
        deadline = time.monotonic() + 1
        view = memoryview(data)
        while view:
            if time.monotonic() > deadline:
                raise TimeoutError('Strategy did not read its input')
            try:
                written = os.write(fd, view)
                view = view[written:]
            except BlockingIOError:
                time.sleep(.001)

    def close(self):
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        if self.stderr_log is not None:
            while True:
                try:
                    data = os.read(self.process.stderr.fileno(), 65536)
                except BlockingIOError:
                    break
                if not data:
                    break
                self.stderr_log.write(data[:max(0, (1 << 20)-self.stderr_bytes)])
                self.stderr_bytes += len(data)
            self.process.stderr.close()


class Resources:
    def __init__(self, submission, model_root=MODEL, fixed_inputs=()):
        import pynvml
        self.nvml = pynvml
        pynvml.nvmlInit()
        if pynvml.nvmlDeviceGetCount() != 1:
            raise RuntimeError('Exactly one mapped GPU is required')
        self.gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.peak_gpu = 0
        self.peak_disk = 0
        self.submission = submission
        self.fixed_bytes = 0
        seen = set()
        fixed_roots = [model_root, Path(__file__).parent, '/task/data', '/task/docs',
                       '/task/baselines', *fixed_inputs]
        for root in map(Path, fixed_roots):
            for p in ([root] if root.is_file() else root.rglob('*')):
                if p.is_file():
                    s = p.stat()
                    identity = (s.st_dev, s.st_ino)
                    if identity not in seen:
                        seen.add(identity)
                        self.fixed_bytes += s.st_size
        self.last_disk = 0
        cgroup = Path('/sys/fs/cgroup')
        maximum = cgroup.joinpath('memory.max').read_text().strip()
        if maximum == 'max' or int(maximum) > 32 << 30:
            raise RuntimeError('A <=32 GiB aggregate container memory cgroup is required')
        self.initial_oom = self.oom_count()

    def oom_count(self):
        events = dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
        return int(events.get('oom_kill', 0))

    def check(self, disk=False):
        used = self.nvml.nvmlDeviceGetMemoryInfo(self.gpu).used
        self.peak_gpu = max(self.peak_gpu, used)
        if used > GPU_LIMIT:
            raise RuntimeError(f'Global resource violation: 24 GiB GPU memory exceeded ({used} bytes)')
        if self.oom_count() != self.initial_oom:
            raise RuntimeError('Global resource violation: aggregate memory OOM')
        now = time.monotonic()
        if disk or now-self.last_disk > .1:
            deadline = now + .2
            total = self.fixed_bytes + sum(isolation.bytes_used(p, deadline)
                for p in (self.submission, '/work'))
            self.last_disk = now
            self.peak_disk = max(self.peak_disk, total)
            if total > STORAGE_LIMIT:
                raise RuntimeError('Global resource violation: 40 GiB task storage exceeded')

    def report(self):
        return {'peak_gpu_bytes': self.peak_gpu, 'peak_task_storage_bytes': self.peak_disk,
                'peak_cgroup_memory_bytes': int(Path('/sys/fs/cgroup/memory.peak').read_text()),
                'gpu_name': self.nvml.nvmlDeviceGetName(self.gpu),
                'gpu_uuid': self.nvml.nvmlDeviceGetUUID(self.gpu)}


class Backend:
    def __init__(self, config, output, resources, startup_seconds=DEPLOY_SECONDS):
        self.resources = resources
        self.log = (output / 'model.stderr').open('ab')
        self.process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('backend.py')),
            str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            env={**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                 'TOKENIZERS_PARALLELISM': 'false'}, start_new_session=True)
        self.pipe = JsonPipe(self.process)
        self.pending = None
        self.broken = False
        try:
            self.info = self.pipe.read(time.monotonic()+startup_seconds, resources.check)
            if self.info.get('ready') is not True:
                raise RuntimeError('Model backend did not become ready')
        except Exception:
            self.close()
            raise

    def request(self, message, spent, candidates, timeout):
        self.pending = None
        try:
            self.pipe.send({'request': message, 'budget': BUDGET, 'already_spent': spent,
                            'candidate_ids': list(candidates)})
            deadline = time.monotonic()+timeout
            reply = self.pipe.read(deadline, self.resources.check)
            if 'reservation' in reply:
                self.pending = reply
                reply = self.pipe.read(deadline, self.resources.check)
            self.pending = None
            if 'model' in reply:
                self.info['model'] = reply['model']
            if any(r['status'] == 'failed' for r in reply.get('calls', [])):
                self.broken = True
            return reply
        except Exception:
            self.broken = True
            self.process.kill()
            self.process.wait(timeout=10)
            raise

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        self.pipe.close()
        self.log.close()


def freeze_submission(path):
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Missing or linked submission directory')
    for p in [root, *root.rglob('*')]:
        s = p.lstat()
        if not stat.S_ISREG(s.st_mode) and not stat.S_ISDIR(s.st_mode):
            raise ValueError('Submission must contain only regular files and directories')
        executable = bool(s.st_mode & 0o111)
        os.chown(p, 0, 0)
        os.chmod(p, 0o555 if p.is_dir() or executable else 0o444)
    script = root / 'run.sh'
    if not script.is_file() or not os.access(script, os.X_OK):
        raise ValueError('run.sh must exist and be executable')
    config = root / 'deployment.json'
    if not config.is_file() or config.stat().st_size > 4096:
        raise ValueError('deployment.json must be a regular JSON file <=4096 bytes')
    deployment_config(config)


def run_query(query, submission, backend, output, resources):
    isolation.cleanup()
    shutil.rmtree('/work', ignore_errors=True)
    Path('/work').mkdir(mode=0o700)
    os.chown('/work', isolation.UID, isolation.UID)
    report = {'query_id': query['query_id'], 'ids': [], 'status': 'failed',
              'spent_tokens': 0, 'calls': [], 'inference_seconds': 0.0}
    process = pipe = None
    started = time.monotonic()
    excluded = 0
    stderr = (output / (query['query_id']+'.stderr')).open('wb')
    cpus = sorted(os.sched_getaffinity(0))[:16]
    env = {'PATH': '/opt/conda/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': '/work',
           'TMPDIR': '/work', 'XDG_CACHE_HOME': '/work', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
           'OMP_NUM_THREADS': str(len(cpus)), 'OPENBLAS_NUM_THREADS': str(len(cpus))}
    try:
        process = subprocess.Popen([str(submission / 'run.sh')], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            preexec_fn=lambda: isolation.isolate('/work', cpus))
        pipe = JsonPipe(process, stderr)
        pipe.send({'type': 'query', **query, 'token_budget': BUDGET,
                   'output_weight': 4})
        while True:
            message = pipe.read(started+excluded+LOCAL_SECONDS, resources.check)
            if isinstance(message, dict) and message.get('type') == 'result':
                report['ids'] = validate_result(message, query)
                report['status'] = 'ok'
                break
            isolation.freeze(started+excluded+LOCAL_SECONDS)
            pause = time.monotonic()
            remaining = INFERENCE_SECONDS-report['inference_seconds']
            if remaining <= 0:
                raise TimeoutError('Cumulative inference deadline exceeded')
            try:
                response = backend.request(message, report['spent_tokens'],
                    {d['doc_id'] for d in query['candidates']}, remaining)
            finally:
                elapsed = time.monotonic()-pause
                excluded += elapsed
                report['inference_seconds'] += elapsed
                if backend.pending is not None:
                    report['spent_tokens'] = backend.pending['meter_spent']
                    report['calls'].append({**backend.pending['reservation'], 'status': 'failed'})
            report['spent_tokens'] = response['meter_spent']
            report['calls'].extend(response['calls'])
            if 'error' in response:
                raise ValueError(response['error'])
            isolation.signal_all(signal.SIGCONT)
            pipe.send(response['reply'])
        # Returning a result also terminates the complete strategy tree.
        report['local_seconds'] = time.monotonic()-started-excluded
        if report['local_seconds'] > LOCAL_SECONDS:
            raise TimeoutError('Cumulative strategy deadline exceeded')
    except Exception as error:
        report.update(status='failed', ids=[], error=str(error))
        report['local_seconds'] = time.monotonic()-started-excluded
        if str(error).startswith('Global resource violation:'):
            raise
    finally:
        isolation.cleanup()
        if process is not None:
            process.wait(timeout=2)
        if pipe is not None:
            pipe.close()
        stderr.close()
    resources.check(disk=True)
    declared = [d for call in report['calls'] for d in call.get('declared_candidate_ids', [])]
    report['declared_unique_candidate_count'] = len(set(declared))
    report['declared_candidate_appearances'] = len(declared)
    return report


def evaluate(submission, queries, qrels, output):
    # Preserve the artifact's own inode so freeze_submission can reject a root
    # symlink before any privileged traversal/chmod. The final path is fixed.
    submission, output = Path(submission).absolute(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    isolation.protect()
    freeze_submission(submission)
    resources = Resources(submission, fixed_inputs=(queries, qrels))
    resources.check(disk=True)
    started = time.monotonic()
    verify_model(MODEL, Path(__file__).with_name('model-hashes.json'))
    backend = None
    report = {'queries': [], 'quality': 0.0}
    try:
        remaining_deploy = DEPLOY_SECONDS-(time.monotonic()-started)
        if remaining_deploy <= 0:
            raise TimeoutError('Deployment hash validation deadline exceeded')
        backend = Backend(submission/'deployment.json', output, resources, remaining_deploy)
        report['deployment_seconds'] = time.monotonic()-started
        if report['deployment_seconds'] > DEPLOY_SECONDS:
            raise TimeoutError('Cumulative model deployment deadline exceeded')
        warm = time.monotonic()
        # Fixed public-only warmup; no hidden query is read before this finishes.
        warmed = backend.request({'type': 'generate', 'messages': [{'role': 'user', 'content': 'Hello.'}],
                                 'max_new_tokens': 1}, 0, set(), WARMUP_SECONDS)
        if 'error' in warmed:
            raise RuntimeError('Warmup failed: '+warmed['error'])
        report['warmup_seconds'] = time.monotonic()-warm
        judgments = json.loads(Path(qrels).read_text())
        opener = gzip.open if str(queries).endswith('.gz') else open
        with opener(queries, 'rt') as f:
            data = [json.loads(line) for line in f]
        for query in data:
            if backend.broken:
                backend.close()
                backend = None
                remaining_deploy = DEPLOY_SECONDS-report['deployment_seconds']
                if remaining_deploy <= 0:
                    raise TimeoutError('Cumulative model redeployment deadline exceeded')
                restart = time.monotonic()
                backend = Backend(submission/'deployment.json', output, resources, remaining_deploy)
                report['deployment_seconds'] += time.monotonic()-restart
                report['backend_restarts'] = report.get('backend_restarts', 0)+1
            result = run_query(query, submission, backend, output, resources)
            result['ndcg_at_10'] = ndcg(result['ids'], judgments[query['query_id']])
            report['queries'].append(result)
            dump(output/'progress.json', report)
            print(json.dumps({'query_id': query['query_id'], 'status': result['status'],
                'ndcg_at_10': result['ndcg_at_10'], 'spent_tokens': result['spent_tokens']}), flush=True)
        report['quality'] = sum(r['ndcg_at_10'] for r in report['queries'])/len(data)
        calls = [c for q in report['queries'] for c in q['calls']]
        report['token_usage'] = {
            'weighted_tokens_total': sum(q['spent_tokens'] for q in report['queries']),
            'max_weighted_tokens_per_query': max(q['spent_tokens'] for q in report['queries']),
            'input_tokens_total': sum(c['input_tokens'] for c in calls),
            'known_output_tokens_total': sum(c['output_tokens'] or 0 for c in calls),
            'unknown_output_call_count': sum(c['output_tokens'] is None for c in calls),
        }
        report['model'] = backend.info
        report['resources'] = resources.report()
        return report
    finally:
        isolation.cleanup()
        if backend is not None:
            backend.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submission', default='/app/submission')
    parser.add_argument('--queries', default='/task/data/public.jsonl.gz')
    parser.add_argument('--qrels', default='/task/data/public-qrels.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = evaluate(args.submission, args.queries, args.qrels, args.output)
    dump(Path(args.output)/'report.json', report)


if __name__ == '__main__':
    main()
