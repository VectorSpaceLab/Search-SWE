"""Public five-pass diagnostics; final isolation and quotas belong to the verifier."""
import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

import numpy as np
import psutil
from repetition import (REPEATS, BUILD_TIMEOUT, LOAD_TIMEOUT, WARMUP_TIMEOUT,
                        QUERY_TIMEOUT, METRICS, median_result)
from scoring import read_qrels, evaluate

SERVING_CAPACITY_BYTES = 40 << 20
ARTIFACT_LIMIT_BYTES = 34 << 20


class Service:
    def __init__(self, command, runtime, environment):
        self.runtime = runtime
        self.started = time.monotonic()
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        env=environment, start_new_session=True, cwd=runtime)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer = bytearray()

    def members(self):
        try:
            parent = psutil.Process(self.process.pid)
            return [parent, *parent.children(recursive=True)]
        except psutil.NoSuchProcess:
            return []

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('response deadline')
        if self.process.poll() is not None:
            raise RuntimeError('service exited')
        return remaining

    def request(self, obj):
        if self.buffer:
            raise ValueError('unsolicited protocol output')
        data = memoryview((json.dumps(obj, separators=(',', ':'), allow_nan=False) + '\n').encode())
        while data:
            self.remaining()
            try:
                data = data[os.write(self.process.stdin.fileno(), data):]
            except BlockingIOError:
                time.sleep(.001)
        while b'\n' not in self.buffer:
            if not self.selector.select(self.remaining()):
                raise TimeoutError('response deadline')
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('service closed stdout')
            self.buffer.extend(chunk)
            if len(self.buffer) > 1 << 20:
                raise ValueError('response exceeds 1 MiB')
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        try:
            return json.loads(line)
        except (ValueError, UnicodeError, RecursionError):
            return None

    def measure(self, requests, timeout, *, initial=False):
        self.phase_start = self.started if initial else time.monotonic()
        self.deadline = self.phase_start + timeout
        for process in self.members():
            try:
                process.send_signal(signal.SIGCONT)
            except psutil.NoSuchProcess:
                pass
        responses = [self.request(request) for request in requests]
        for _ in range(10):
            for process in self.members():
                try:
                    process.send_signal(signal.SIGSTOP)
                except psutil.NoSuchProcess:
                    pass
            stopped = True
            for process in self.members():
                try:
                    stopped &= process.status() in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE)
                except psutil.NoSuchProcess:
                    pass
            if stopped:
                break
            time.sleep(.001)
        else:
            raise RuntimeError('cannot suspend service processes')
        seconds = time.monotonic() - self.phase_start
        if seconds > timeout:
            raise TimeoutError('response deadline')
        return responses, seconds

    def close(self):
        members = self.members()
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for process in members:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        self.process.wait(timeout=5)
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        shutil.rmtree(self.runtime)


def allocated_bytes(root):
    total, seen = 0, set()
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            info = path.stat()
            identity = info.st_dev, info.st_ino
            if identity not in seen:
                seen.add(identity)
                total += max(info.st_size, info.st_blocks * 512)
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submission', type=Path, default=Path('/app/submission'))
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=Path('/task/data'))
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    submission, index, data = args.submission.resolve(), args.index_dir.resolve(), args.data_dir.resolve()
    index.mkdir(parents=True, exist_ok=True)
    build_runtime = index.parent / (index.name + '-build-runtime')
    build_runtime.mkdir(exist_ok=True)
    environment = dict(os.environ, TMPDIR=str(build_runtime), HOME=str(build_runtime))
    report = {'queries': [], 'query_repeats': REPEATS,
              'scope': 'five independent serving passes; final physical quotas and privilege isolation are not simulated',
              'artifact_limit_bytes': ARTIFACT_LIMIT_BYTES, 'serving_capacity_bytes': SERVING_CAPACITY_BYTES}
    if not args.skip_build:
        start = time.monotonic()
        process = subprocess.Popen([str(submission / 'build.sh'), '--data-dir', str(data), '--index-dir', str(index)],
                                   env=environment, start_new_session=True)
        try:
            if process.wait(timeout=BUILD_TIMEOUT):
                raise RuntimeError('build failed')
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        report['build_seconds'] = time.monotonic() - start
    report['submission_and_index_bytes'] = allocated_bytes(submission) + allocated_bytes(index)
    if report['submission_and_index_bytes'] > ARTIFACT_LIMIT_BYTES:
        report.update(score=0, ndcg_prime=0, error='prepared artifact limit: submission and index exceed 34 MiB')
    else:
        for name in ('OPENROUTER_API_KEY', 'JINA_API_KEY', 'OPENROUTER_API_BASE_URL'):
            environment.pop(name, None)
        labels = read_qrels(data / 'validation/qrels.tsv')
        mapping = np.load(data / 'instance_visual.npy', mmap_mode='r')
        queries = [json.loads(line) for line in (data / 'validation/queries.jsonl').read_text().splitlines()]
        attempts = {query['query_id']: [] for query in queries}

        def load_service():
            runtime = Path(tempfile.mkdtemp(prefix=index.name + '-serve-', dir=index.parent))
            env = dict(environment, TMPDIR=str(runtime), HOME=str(runtime))
            service = Service([str(submission / 'serve.sh')], runtime, env)
            try:
                response, load = service.measure([{'op': 'load', 'data_dir': str(data),
                                                   'index_dir': str(index), 'work_dir': str(runtime)}],
                                                 LOAD_TIMEOUT, initial=True)
                if response != [{'ok': True}]:
                    raise ValueError('expected load acknowledgment')
                _, warm = service.measure([{'op': 'query', **q} for q in queries[:3]], WARMUP_TIMEOUT)
                report.setdefault('loads', []).append({'load_seconds': load, 'warmup_seconds': warm})
                return service
            except BaseException:
                service.close()
                raise

        service = None
        try:
            for repeat in range(REPEATS):
                service = load_service()
                for query in queries:
                    result = {'repeat': repeat + 1, 'valid': False, **{metric: 0.0 for metric in METRICS}}
                    try:
                        if service is None:
                            service = load_service()
                        answers, seconds = service.measure([{'op': 'query', **query}], QUERY_TIMEOUT)
                        result.update(evaluate(answers[0], query['query_id'], mapping, labels[query['query_id']]), seconds=seconds)
                        if not result['valid']:
                            service.close()
                            service = None
                    except (TimeoutError, RuntimeError, ValueError, OSError) as error:
                        result['error'] = f'{type(error).__name__}: {error}'
                        if service:
                            result['seconds'] = time.monotonic() - service.phase_start
                            service.close()
                            service = None
                    attempts[query['query_id']].append(result)
                if service:
                    service.close()
                    service = None
            report['queries'] = [{'query_id': query['query_id'], **median_result(attempts[query['query_id']])}
                                 for query in queries]
        except (TimeoutError, RuntimeError, ValueError, OSError) as error:
            report['error'] = f'{type(error).__name__}: {error}'
            report['attempts'] = attempts
        finally:
            if service:
                service.close()
        for metric in METRICS:
            report[metric] = sum(q[metric] for q in report['queries']) / len(queries)
        report['score'] = 100 * report['ndcg_prime']
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(payload)
    print(payload)


if __name__ == '__main__':
    main()
