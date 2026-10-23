"""Profile a persistent submission on public vectors across successive inserts.

This tool measures latency and framing, not retrieval quality or a task score.
Queries and duplicate inserts are sampled only from the public initial matrix.
Use the default ten stages/1000 queries for capacity tests. Hidden-query latency
can differ; the default target reserves 10% against the tightest official cell.
Run as root in the agent container, with output outside /app/submission:
  python /task/tools/profile_public.py --dimensions 3072 --output /app/profiles/r1 \
      -- bash /app/submission/run.sh
"""
import argparse
import hashlib
import json
from runtime_limits import LIMITS
import math
import os
from pathlib import Path
import resource
import select
import signal
import subprocess
import time

import numpy as np


KS = (100, 200, 400, 800, 1000)
UID = 10001
MAX_LINE = 128 * 1024


def pin_group(group, cpus):
    threads = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            stat = (process / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) == group:
                threads.extend(int(t.name) for t in (process / 'task').iterdir())
        except (FileNotFoundError, ProcessLookupError):
            pass
    previous = os.geteuid()
    try:
        os.seteuid(UID)
        for thread in threads:
            try:
                os.sched_setaffinity(thread, cpus)
            except ProcessLookupError:
                pass
    finally:
        os.seteuid(previous)


class Worker:
    def __init__(self, command, state, stderr, cpus):
        def prepare():
            os.sched_setaffinity(0, cpus)
            os.setgroups([])
            os.setgid(UID)
            os.setuid(UID)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**3,) * 2)
        env = {'PATH': '/opt/conda/bin:/usr/bin:/bin', 'HOME': str(state),
               'TMPDIR': str(state), 'OMP_NUM_THREADS': '16',
               'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
               'KMP_AFFINITY': 'disabled', 'OMP_PROC_BIND': 'false',
               'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C.UTF-8'}
        self.stderr = stderr.open('wb')
        self.started = time.monotonic()
        self.child = subprocess.Popen(command, cwd=state, env=env,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self.stderr, start_new_session=True,
                                      preexec_fn=prepare, bufsize=0)
        os.set_blocking(self.child.stdin.fileno(), False)
        os.set_blocking(self.child.stdout.fileno(), False)
        self.buffer = bytearray()

    def request(self, value, deadline):
        if self.buffer:
            raise ValueError('Unsolicited stdout after a response')
        payload = memoryview((json.dumps(value, separators=(',', ':'),
                                         allow_nan=False) + '\n').encode())
        while payload:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Request exceeded diagnostic target')
            if select.select([], [self.child.stdin], [], min(.05, remaining))[1]:
                try:
                    payload = payload[os.write(self.child.stdin.fileno(), payload):]
                except BlockingIOError:
                    pass
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Response exceeded diagnostic target')
            if select.select([self.child.stdout], [], [], min(.05, remaining))[0]:
                chunk = os.read(self.child.stdout.fileno(), MAX_LINE + 1)
                if not chunk:
                    raise ValueError('Submission exited before its response')
                self.buffer.extend(chunk)
                if len(self.buffer) > MAX_LINE:
                    raise ValueError('Response exceeds 128 KiB')
        line, _, extra = self.buffer.partition(b'\n')
        self.buffer = bytearray(extra)
        return json.loads(line)

    def pause(self):
        os.killpg(self.child.pid, signal.SIGSTOP)
        deadline = time.monotonic() + 2
        while self.child.poll() is None:
            status = Path(f'/proc/{self.child.pid}/status').read_text()
            if '\nState:\tT ' in status:
                return
            if time.monotonic() > deadline:
                raise RuntimeError('Unable to pause submission')
            time.sleep(.001)
        raise ValueError('Submission exited')

    def resume(self):
        os.killpg(self.child.pid, signal.SIGCONT)

    def close(self):
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.child.wait(timeout=5)
        self.child.stdin.close()
        self.child.stdout.close()
        self.stderr.close()


def validate_responses(responses, k, live):
    returned = 0
    for response in responses:
        if not isinstance(response, dict):
            raise ValueError('Search response must be an object')
        ids, distances = response.get('ids'), response.get('distances')
        if not isinstance(ids, list) or not isinstance(distances, list):
            raise ValueError('Search response requires ids and distances lists')
        if len(ids) != len(distances) or len(ids) > k:
            raise ValueError('Invalid result lengths')
        if len(set(ids)) != len(ids) or any(type(i) is not int or not 0 <= i < live for i in ids):
            raise ValueError('Duplicate or invalid IDs')
        if any(type(d) not in (int, float) or not math.isfinite(d) or d < 0 for d in distances):
            raise ValueError('Distances must be finite nonnegative numbers')
        returned += len(ids)
    return returned / len(responses)


def profile(args, calibration, dimension, output):
    initial_path = args.public_root / str(dimension) / 'initial.npy'
    initial = np.load(initial_path, mmap_mode='r', allow_pickle=False)
    if initial.dtype != np.float32 or initial.ndim != 2 or initial.shape[1] != dimension:
        raise ValueError('Invalid public initial matrix')
    needed = args.stages * (args.batch_size + args.queries)
    if needed > len(initial):
        raise ValueError('Not enough initial rows for disjoint public probe samples')
    rows = np.random.Generator(np.random.PCG64(20261021 + dimension)).choice(
        len(initial), needed, replace=False)
    split = args.stages * args.batch_size
    inserts = initial[rows[:split]]
    queries = initial[rows[split:]]
    state, events = output / 'state', output / 'events'
    state.mkdir(mode=0o755)
    events.mkdir(mode=0o755)
    state.chmod(0o755)
    events.chmod(0o755)
    os.chown(state, UID, UID)
    cpus = set(calibration['cpu_affinity'])
    limits = calibration['datasets'][str(dimension)]
    worker = Worker(args.command, state, output / 'stderr.log', cpus)
    result = {'dimension': dimension, 'cells': [], 'insert_seconds': [],
              'score_available': False, 'quality_checked': False,
              'query_source': 'distinct public initial rows',
              'insert_source': 'public initial rows reinserted with new IDs',
              'stages': args.stages, 'queries_per_stage': args.queries,
              'batch_size': args.batch_size, 'pid': worker.child.pid}
    phase = {'operation': 'build'}
    phase_started = worker.started
    phase_limit = limits['build_seconds']
    try:
        deadline = worker.started + limits['build_seconds']
        ack = worker.request({'op': 'build', 'vectors': str(initial_path),
                              'dimension': dimension, 'count': len(initial),
                              'threads': 16, 'state_dir': str(state)}, deadline)
        if ack != {'ok': True}:
            raise ValueError('Build did not acknowledge readiness')
        pin_group(worker.child.pid, {min(cpus)})
        for query in np.load(args.public_root / str(dimension) / 'warmup.npy', allow_pickle=False):
            worker.request({'op': 'search', 'vector': query.tolist(), 'k': 1000}, deadline)
        worker.pause()
        result['build_seconds'] = time.monotonic() - worker.started
        if result['build_seconds'] > limits['build_seconds']:
            raise TimeoutError('Build including public warmup exceeded its budget')
        for stage in range(args.stages):
            phase = {'operation': 'insert', 'stage': stage}
            pin_group(worker.child.pid, cpus)
            event = events / 'insert.npy'
            np.save(event, inserts[stage * args.batch_size:(stage + 1) * args.batch_size])
            event.chmod(0o444)
            started = time.monotonic()
            phase_started = started
            phase_limit = limits['insert_seconds']
            worker.resume()
            ack = worker.request({'op': 'insert', 'vectors': str(event),
                                  'count': args.batch_size,
                                  'first_id': len(initial) + stage * args.batch_size,
                                  'threads': 16}, started + limits['insert_seconds'])
            worker.pause()
            result['insert_seconds'].append(time.monotonic() - started)
            if ack != {'ok': True}:
                raise ValueError('Insertion did not acknowledge readiness')
            if result['insert_seconds'][-1] > limits['insert_seconds']:
                raise TimeoutError('Insertion exceeded its budget')
            event.unlink()
            pin_group(worker.child.pid, {min(cpus)})
            for ki, k in enumerate(KS):
                phase = {'operation': 'query', 'stage': stage, 'k': k}
                official_minimum = calibration['exact_scan_fraction'] * min(
                    row[ki] for row in limits['full_scan_seconds'])
                target = official_minimum * (1 - args.headroom) * args.queries / 1000
                started = time.monotonic()
                phase_started = started
                phase_limit = target
                worker.resume()
                responses = [worker.request({'op': 'search', 'vector': query.tolist(), 'k': k},
                                            started + target)
                             for query in queries[stage * args.queries:(stage + 1) * args.queries]]
                worker.pause()
                seconds = time.monotonic() - started
                mean_returned = validate_responses(responses, k,
                                                   len(initial) + (stage + 1) * args.batch_size)
                cell = {'stage': stage, 'k': k, 'seconds': seconds,
                        'official_minimum_1000_query_seconds': official_minimum,
                        'diagnostic_target_seconds': target,
                        'mean_returned': mean_returned}
                result['cells'].append(cell)
                print(json.dumps({'dimension': dimension, **cell}), flush=True)
                (output / 'progress.json').write_text(json.dumps(result, indent=2) + '\n')
                if seconds > target:
                    raise TimeoutError('Cell exceeded diagnostic target')
        result['status'] = 'complete'
    except (ValueError, TypeError, OSError, TimeoutError, RuntimeError) as error:
        result.update(status='failed', failure=str(error), failure_context=phase,
                      failure_type=type(error).__name__,
                      failure_elapsed_seconds=time.monotonic() - phase_started,
                      failure_target_seconds=phase_limit)
    finally:
        worker.close()
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dimensions', type=int, nargs='+', default=[1536, 3072])
    parser.add_argument('--public-root', type=Path, default=Path('/task/public'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stages', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--queries', type=int, default=1000)
    parser.add_argument('--headroom', type=float, default=.1)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ['--']:
        args.command = args.command[1:]
    if not args.command or not 1 <= args.stages <= 10 or not 1 <= args.queries <= 1000:
        parser.error('Provide a command, 1..10 stages and 1..1000 queries')
    if not 1 <= args.batch_size <= 1000 or not 0 <= args.headroom < .5:
        parser.error('Invalid batch size or headroom')
    if os.geteuid() != 0:
        parser.error('Run the profiling supervisor as root; the submission runs as UID 10001')
    args.output = args.output.resolve()
    args.public_root = args.public_root.resolve()
    calibration = LIMITS
    cpus = set(calibration['cpu_affinity'])
    if len(cpus) != 16 or not cpus <= os.sched_getaffinity(0):
        parser.error('Use the same 16-CPU allocation as calibration')
    os.sched_setaffinity(0, cpus)
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Use a fresh output directory')
    new_directories = []
    parent = args.output
    while not parent.exists():
        new_directories.append(parent)
        parent = parent.parent
    args.output.mkdir(parents=True, exist_ok=True, mode=0o755)
    for directory in new_directories:
        directory.chmod(0o755)
    args.output.chmod(0o755)
    for directory in (args.output, *args.output.parents):
        st = directory.stat()
        execute = (st.st_mode & 0o100 if st.st_uid == UID else
                   st.st_mode & 0o010 if st.st_gid == UID else st.st_mode & 0o001)
        if not execute:
            parser.error('Output ancestors must be traversable by UID 10001; use a fresh path under /app')
    results = {}
    for dimension in args.dimensions:
        output = args.output / str(dimension)
        output.mkdir(mode=0o755)
        output.chmod(0o755)
        results[str(dimension)] = profile(args, calibration, dimension, output)
    summary = {'score_available': False, 'quality_checked': False,
               'limits_sha256': hashlib.sha256(json.dumps(calibration, sort_keys=True).encode()).hexdigest(),
               'headroom': args.headroom,
               'full_profile_size': args.stages == 10 and args.queries == args.batch_size == 1000,
               'notice': 'Public probes are not hidden queries; passing is not a hidden-latency guarantee.',
               'datasets': results}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if all(r['status'] == 'complete' for r in results.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
