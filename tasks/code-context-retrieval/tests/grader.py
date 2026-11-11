"""Root-owned supervisor; submitted commands execute as the dedicated UID 10001."""
import json
import math
import os
from pathlib import Path
import random
import signal
import stat
import subprocess
import threading
import time
import traceback

from scoring import line_set, load_files, parse_json, read_jsonl, score_one

UID = 10001
APP = Path('/app')
INDEX = APP / 'index'
WORK = Path('/work')
LOGS = Path('/logs/verifier')
CORPUS = Path('/task/data/repos')
BUILD_SECONDS = 3600
QUERY_SECONDS = 180
QUERY_COUNT = 20


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def cleanup():
    # This UID belongs only to this submission inside its disposable container.
    for status in Path('/proc').glob('[0-9]*/status'):
        try:
            uid = next(s for s in status.read_text().splitlines() if s.startswith('Uid:'))
            if int(uid.split()[1]) == UID:
                os.kill(int(status.parent.name), signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def prepare():
    if os.getuid() != 0 or not Path('/.dockerenv').exists():
        raise RuntimeError('Run only in a disposable root-owned verifier container')
    if APP.is_symlink() or not APP.is_dir():
        raise ValueError('Missing or invalid /app')
    # Freeze transferred artifacts, including symlink ownership; never follow them.
    for root, dirs, files in os.walk(APP, followlinks=False):
        os.chown(root, 0, 0)
        os.chmod(root, 0o755)
        for name in dirs + files:
            path = Path(root) / name
            mode = path.lstat().st_mode
            os.chown(path, 0, 0, follow_symlinks=False)
            if stat.S_ISREG(mode):
                os.chmod(path, 0o755 if mode & 0o111 else 0o644)
            elif not (stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                raise ValueError('Special files in submission')
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
    for name in ('build.sh', 'run.sh'):
        path = APP / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_mode & 0o111:
            raise ValueError(f'Missing executable {name}')
    # Agent-created indexes never substitute for construction in the fresh verifier.
    if INDEX.exists() or INDEX.is_symlink():
        import shutil
        if INDEX.is_symlink() or not INDEX.is_dir():
            INDEX.unlink()
        else:
            shutil.rmtree(INDEX)
    INDEX.mkdir(mode=0o700)
    os.chown(INDEX, UID, UID)
    (INDEX / 'tmp').mkdir(mode=0o700)
    os.chown(INDEX / 'tmp', UID, UID)
    WORK.mkdir(exist_ok=True)
    os.chown(WORK, 0, 0)
    os.chmod(WORK, 0o755)
    # The trajectory, if collected, is evidence and cannot be rewritten by a solver.
    agent_logs = Path('/logs/agent')
    if agent_logs.is_dir() and not agent_logs.is_symlink():
        os.chown(agent_logs, 0, 0)
        os.chmod(agent_logs, 0o700)


def child_env():
    env = {'HOME': str(INDEX), 'USER': 'submission', 'LOGNAME': 'submission',
           'JAVA_HOME': '/opt/java/openjdk',
           'PATH': '/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'TMPDIR': str(INDEX / 'tmp'), 'XDG_CACHE_HOME': str(INDEX / 'cache'),
           'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'OMP_NUM_THREADS': '16', 'OPENBLAS_NUM_THREADS': '16',
           'TOKENIZERS_PARALLELISM': 'false'}
    for name in ('OPENROUTER_API_KEY', 'JINA_API_KEY', 'http_proxy', 'https_proxy',
                 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'no_proxy'):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def capture(stream, path):
    # Bound retained diagnostics without stopping the submitted process's output.
    remaining = 1024 * 1024
    with path.open('wb') as out:
        while block := stream.read(8192):
            out.write(block[:remaining])
            remaining = max(0, remaining - len(block))


def run(command, timeout, prefix):
    started = time.monotonic()
    process = subprocess.Popen(['/usr/bin/setpriv', '--no-new-privs', '--', *command],
                               cwd=APP, env=child_env(), user=UID, group=UID,
                               extra_groups=[], umask=0o077, start_new_session=True,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    threads = []
    for stream, suffix in [(process.stdout, 'stdout'), (process.stderr, 'stderr')]:
        thread = threading.Thread(target=capture, args=(stream, LOGS / f'{prefix}.{suffix}.log'), daemon=True)
        thread.start()
        threads.append(thread)
    timeout_hit = False
    try:
        code = process.wait(timeout=max(0., timeout - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        timeout_hit = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        code = process.wait(timeout=5)
    elapsed = time.monotonic() - started
    for thread in threads:
        thread.join(timeout=.1)
    return {'returncode': code, 'seconds': elapsed, 'timed_out': timeout_hit or elapsed > timeout}


def read_output(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Output must be a regular file')
        rows = [parse_json(line) for line in stream if line.strip()]
    if len(rows) != 1:
        raise ValueError('Expected exactly one result for the supplied query')
    return rows[0]


def evaluate():
    prepare()
    files = load_files(CORPUS)
    queries = read_jsonl(Path('/tests/data/queries.jsonl'))
    labels = read_jsonl(Path('/tests/data/ground_truth.jsonl'))
    gold = {r['query_id']: r['regions'] for r in labels}
    assert len(queries) == len(labels) == len(gold) == QUERY_COUNT
    assert len({q['query_id'] for q in queries}) == QUERY_COUNT
    assert set(gold) == {q['query_id'] for q in queries}
    for q in queries:
        assert isinstance(q['text'], str) and q['text']
        assert line_set(gold[q['query_id']], files[q['snapshot_id']])
    report = {'query_count': QUERY_COUNT, 'reward': 0., 'queries': []}
    report['build'] = run([str(APP / 'build.sh'), '--corpus', str(CORPUS),
                           '--index-dir', str(INDEX)], BUILD_SECONDS, 'build')
    if report['build']['returncode'] or report['build']['timed_out']:
        report['error'] = 'Build failed or exceeded its deadline'
        return report
    random.SystemRandom().shuffle(queries)
    for ordinal, query in enumerate(queries):
        qid = query['query_id']
        runtime_id = 'q_' + os.urandom(16).hex()
        folder = WORK / runtime_id
        folder.mkdir(mode=0o755)
        input_path = folder / 'query.jsonl'
        input_path.write_text(json.dumps({**query, 'query_id': runtime_id}, ensure_ascii=False) + '\n')
        input_path.chmod(0o444)
        output_dir = folder / 'output'
        output_dir.mkdir(mode=0o700)
        os.chown(output_dir, UID, UID)
        output_path = output_dir / 'result.jsonl'
        result = {'query_id': qid, 'valid': False, 'f1': 0., 'precision': 0., 'recall': 0.}
        try:
            execution = run([str(APP / 'run.sh'), '--index-dir', str(INDEX),
                             '--queries', str(input_path), '--output', str(output_path),
                             '--top-k', '5'], QUERY_SECONDS, f'query-{ordinal:02d}')
            result.update(execution)
            if execution['timed_out']:
                raise TimeoutError('Query exceeded 180 seconds')
            if execution['returncode']:
                raise ValueError('Query process returned nonzero')
            prediction = read_output(output_path)
            result.update(score_one(prediction, gold[qid], files[query['snapshot_id']], runtime_id))
            # Only schema-valid predictions enter trusted JSON reports. Malformed
            # payloads must not prevent subsequent questions from being evaluated.
            if result['valid']:
                result['prediction'] = prediction
        except (OSError, ValueError, TypeError, TimeoutError, RecursionError) as error:
            result['error'] = f'{type(error).__name__}: {error}'
        report['queries'].append(result)
        write_json(LOGS / 'evaluation.json', report)
    report['reward'] = sum(q['f1'] for q in report['queries']) / QUERY_COUNT
    report['valid_fraction'] = sum(q['valid'] for q in report['queries']) / QUERY_COUNT
    return report


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    os.chmod(LOGS, 0o700)
    (LOGS / 'reward.txt').write_text('0\n')
    write_json(LOGS / 'reward.json', {'reward': 0., 'line_f1': 0.})
    try:
        report = evaluate()
        reward = report['reward']
        assert math.isfinite(reward) and 0 <= reward <= 1
    except Exception as error:
        report = {'reward': 0., 'error': f'{type(error).__name__}: {error}'}
        (LOGS / 'failure.log').write_text(traceback.format_exc())
    finally:
        cleanup()
    write_json(LOGS / 'evaluation.json', report)
    reward = report['reward']
    write_json(LOGS / 'reward.json', {'reward': reward, 'line_f1': reward})
    (LOGS / 'reward.txt').write_text(f'{reward:.12f}\n')
    return int('error' in report)


if __name__ == '__main__':
    raise SystemExit(main())
