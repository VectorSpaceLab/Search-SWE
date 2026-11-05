"""Root-owned evaluator; only submitted build/search processes run as UID 10001."""
import json
import math
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, '/tests')
from score import load_catalog, lookup, parse_json, score_one

UID = 10001
SUBMISSION = Path('/app/submission')
INDEX = Path('/work/index')
CORPUS = Path('/task/data/catalog.json')
LOGS = Path('/logs/verifier')
BUILD_SECONDS = 1200
READY_SECONDS = 30
QUERY_SECONDS = 20.0
MAX_LINE = 65536
MAX_INDEX = 8 * 1024**3
ENV = {'HOME': '/home/submission', 'USER': 'submission', 'LOGNAME': 'submission',
       'PATH': '/opt/conda/bin:/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
       'PYTHONUNBUFFERED': '1', 'OMP_NUM_THREADS': '16', 'OPENBLAS_NUM_THREADS': '16',
       'TOKENIZERS_PARALLELISM': 'false', 'TMPDIR': '/work/tmp'}


class SubmissionFailure(ValueError):
    """A documented submission gate failed, rather than the verifier itself."""


def submission_env():
    # Forward only the public task API resources, never coding-agent/judge keys.
    env = ENV.copy()
    for key in ('OPENROUTER_API_KEY', 'JINA_API_KEY', 'OPENROUTER_API_BASE_URL'):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def cleanup_children():
    # This UID is dedicated to submitted processes in the disposable verifier.
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            uid = next(line for line in path.read_text().splitlines() if line.startswith('Uid:'))
            if int(uid.split()[1]) == UID:
                os.kill(int(path.parent.name), signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def readable_submission():
    if SUBMISSION.is_symlink() or not SUBMISSION.is_dir():
        raise SubmissionFailure('Missing submission directory')
    for root, dirs, files in os.walk(SUBMISSION, followlinks=False):
        os.chown(root, 0, 0)
        os.chmod(root, 0o755)
        for name in files:
            path = Path(root) / name
            mode = path.lstat().st_mode
            if stat.S_ISREG(mode):
                os.chown(path, 0, 0)
                os.chmod(path, 0o755 if mode & 0o111 else 0o644)
            elif not stat.S_ISLNK(mode):
                raise SubmissionFailure('Submission contains a special file')
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]


def index_size():
    total = 0
    for root, dirs, files in os.walk(INDEX, followlinks=False):
        for name in dirs + files:
            path = Path(root) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise SubmissionFailure('Index must contain only regular files and directories')
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
        if total > MAX_INDEX:
            raise SubmissionFailure('Index exceeds 8 GiB')
    return total


def drain(stream, destination):
    with open(destination, 'wb') as out:
        remaining = MAX_LINE
        while chunk := stream.read(8192):
            if remaining:
                out.write(chunk[:remaining])
                remaining -= min(remaining, len(chunk))


def launch(command, log_prefix, stdout_pipe=True):
    process = subprocess.Popen(['/opt/conda/bin/python', '-I', '/runner/launch.py', *command],
                               cwd=SUBMISSION, env=submission_env(),
                               stdin=subprocess.PIPE if stdout_pipe else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                               user=UID, group=UID, extra_groups=[], umask=0o077,
                               start_new_session=True)
    streams = [(process.stderr, 'stderr')]
    if not stdout_pipe:
        streams.append((process.stdout, 'stdout'))
    process.capture_threads = []
    for stream, suffix in streams:
        thread = threading.Thread(target=drain, args=(stream, LOGS / f'{log_prefix}.{suffix}.log'), daemon=True)
        thread.start()
        process.capture_threads.append(thread)
    return process


def close_process(process):
    cleanup_children()
    process.wait(timeout=5)
    for thread in process.capture_threads:
        thread.join(timeout=1)
    for stream in [process.stdin, process.stdout, process.stderr]:
        if stream is not None:
            stream.close()


class Server:
    def __init__(self, number):
        self.process = launch(['/bin/bash', str(SUBMISSION / 'search.sh'), '--index-dir', str(INDEX)],
                              f'server-{number}')
        self.buffer = b''
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stdin.fileno(), False)
        try:
            ready = parse_json(self.line(READY_SECONDS))
            if not isinstance(ready, dict) or set(ready) != {'ready'} or ready['ready'] is not True:
                raise ValueError('Expected exactly {"ready": true} on startup')
        except Exception:
            self.close()
            raise

    def line(self, timeout):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError('Response deadline exceeded')
            chunk = os.read(self.process.stdout.fileno(), 8192)
            if not chunk:
                raise ValueError('Search process closed stdout')
            self.buffer += chunk
            if len(self.buffer) > MAX_LINE:
                raise ValueError('Response exceeds 65536 bytes')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line.decode('utf-8')

    def query(self, row):
        start = time.monotonic()
        payload = (json.dumps(row) + '\n').encode()
        if os.write(self.process.stdin.fileno(), payload) != len(payload):
            raise ValueError('Search process is not consuming input')
        result = parse_json(self.line(max(0, QUERY_SECONDS - (time.monotonic() - start))))
        return result, time.monotonic() - start

    def close(self):
        self.selector.close()
        close_process(self.process)


def evaluate():
    readable_submission()
    for path in [INDEX, Path('/work/tmp')]:
        path.mkdir(parents=True, exist_ok=False)
        os.chown(path, UID, UID)
        os.chmod(path, 0o700)
    labels = [json.loads(line) for line in Path('/tests/data/labels.jsonl').read_text().splitlines()]
    queries = [json.loads(line) for line in Path('/tests/data/queries.jsonl').read_text().splitlines()]
    gold = {r['query_id']: r for r in labels}
    assert len(queries) == len(gold) == 10
    catalog_lookup = lookup(load_catalog(CORPUS))
    report = {'status': 'ok', 'valid': True, 'n': len(queries), 'reward': 0.0,
              'table_success_rate': 0.0, 'valid_fraction': 0.0, 'queries': []}
    started = time.monotonic()
    builder = launch(['/bin/bash', str(SUBMISSION / 'build.sh'), '--corpus', str(CORPUS),
                      '--index-dir', str(INDEX)], 'build', stdout_pipe=False)
    try:
        while builder.poll() is None:
            if time.monotonic() - started > BUILD_SECONDS:
                raise SubmissionFailure('Index build exceeded 1200 seconds')
            index_size()
            time.sleep(0.1)
        if builder.returncode:
            raise SubmissionFailure(f'Index build exited with code {builder.returncode}')
        report['index_bytes'] = index_size()
    finally:
        close_process(builder)
    report['build_seconds'] = time.monotonic() - started
    # Preserve the frozen query-file order so service/cache state is reproducible.
    server = None
    server_number = 0
    durations = []
    try:
        for query in queries:
            qid = query['query_id']
            try:
                if server is None:
                    server_number += 1
                    server = Server(server_number)
                    # One synthetic, unscored warm-up; hidden questions never enter a batch file.
                    warmup_id = 'warm_' + os.urandom(12).hex()
                    try:
                        warmup, _ = server.query({'query_id': warmup_id, 'question': 'Find tables containing names.'})
                        if warmup.get('query_id') != warmup_id:
                            raise ValueError('Warm-up query ID mismatch')
                    except Exception as error:
                        # Warm-up is unscored: discard its process and still send
                        # the real query with its own full deadline.
                        report.setdefault('warmup_failures', []).append({
                            'server_number': server_number,
                            'error': f'{type(error).__name__}: {error}',
                        })
                        server.close()
                        server = None
                        server_number += 1
                        server = Server(server_number)
                runtime_id = 'run_' + os.urandom(12).hex()
                prediction, duration = server.query({'query_id': runtime_id, 'question': query['question']})
                result = score_one(prediction, gold[qid], catalog_lookup, runtime_id)
                result['seconds'] = duration
                durations.append(duration)
            except Exception as error:
                result = {'valid': False, 'table_success': 0, 'joint_success': 0,
                          'error': f'{type(error).__name__}: {error}'}
                if server is not None:
                    server.close()
                else:
                    cleanup_children()
                server = None
            report['queries'].append({'query_id': qid, **result})
    finally:
        if server is not None:
            server.close()
        cleanup_children()
    # Recheck index size after serving: no undetected growth beyond the public limit.
    report['index_bytes'] = index_size()
    for metric, key in [('reward', 'joint_success'), ('table_success_rate', 'table_success'), ('valid_fraction', 'valid')]:
        report[metric] = sum(r[key] for r in report['queries']) / len(queries)
    report['warm_p95_seconds_completed_responses'] = sorted(durations)[math.ceil(.95 * len(durations)) - 1] if durations else None
    return report


def main():
    if os.getuid() != 0 or not Path('/.dockerenv').exists():
        raise RuntimeError('Run only as root inside the disposable verifier container')
    LOGS.mkdir(parents=True, exist_ok=True)
    os.chmod('/logs', 0o755)
    os.chmod(LOGS, 0o700)
    (LOGS / 'reward.txt').write_text('0\n')
    try:
        report = evaluate()
    except Exception as error:
        cleanup_children()
        status = 'submission_failed' if isinstance(error, SubmissionFailure) else 'infrastructure_error'
        report = {'status': status, 'valid': False, 'n': 10, 'reward': 0.0,
                  'error': f'{type(error).__name__}: {error}'}
        (LOGS / 'failure.log').write_text(traceback.format_exc())
    assert math.isfinite(report['reward']) and 0 <= report['reward'] <= 1
    (LOGS / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    # Only finalize_reward.py may release a positive reward after the audit.
    print(json.dumps({k: v for k, v in report.items() if k != 'queries'}))
    return int(report['status'] == 'infrastructure_error')


if __name__ == '__main__':
    raise SystemExit(main())
