#!/usr/bin/env python3
"""Automatic host preparation, called by the normal evaluation launcher."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'search-swe-local:incremental-vector-preparation'
CPU_VARIABLE = 'INCREMENTAL_VECTOR_CPUSET'
PLATFORM_VARIABLE = 'INCREMENTAL_VECTOR_PLATFORM_ROOT'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cpu_set(value):
    available = os.sched_getaffinity(0)
    if value:
        selected = set()
        for item in value.split(','):
            if not re.fullmatch(r'\d+(?:-\d+)?', item):
                raise ValueError('CPU allocation must contain IDs or ranges')
            bounds = list(map(int, item.split('-')))
            first, last = bounds[0], bounds[-1]
            if last < first or last > max(available):
                raise ValueError('Unavailable CPU allocation')
            selected.update(range(first, last + 1))
    else:
        selected = set(sorted(available)[:16])
    if len(selected) != 16 or not selected <= available:
        raise ValueError('Exactly 16 available logical CPUs are required')
    return ','.join(map(str, sorted(selected)))


def prepare_inputs(root):
    """Verify finished files and fix public read permissions before read-only mounts."""
    manifest = json.loads((root / 'assets.json').read_text())
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid input path')
        path = root / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f'Input must not be a symbolic link: {relative}')
        if not path.is_file() or path.stat().st_size != entry['size_bytes'] or digest(path) != entry['sha256']:
            raise ValueError(f'Missing or changed input {relative}; restore task assets with the standard downloader')
    for name in ('data/corpus', 'data/validation', 'environment/docs'):
        directory = root / name
        for path in (directory, *directory.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Public resource must not be a symbolic link: {path}')
            path.chmod(0o755 if path.is_dir() else 0o644)
    (root / 'environment').chmod(0o755)
    for name in ('exact_search.py', 'baseline_search.py', 'profile_public.py', 'runtime_limits.py'):
        (root / 'environment' / name).chmod(0o644)


def container(root, cpus, *, output=None, cache_key=False):
    name = 'searchswe-incremental-prepare-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '--name', name, '--network', 'none',
               '--cpus', '16', '--cpuset-cpus', cpus, '--memory', '32g',
               '--memory-swap', '32g', '--pids-limit', '256',
               '--entrypoint', '/opt/conda/bin/python']
    mounts = [(root / 'data/corpus', '/task/data/corpus'),
              (root / 'data/validation', '/task/data/validation'),
              (root / 'tests/data', '/tests/data'),
              (root / 'environment', '/task/reference'),
              (root / 'assets.json', '/task/assets.json')]
    for source, target in mounts:
        command += ['--mount', f'type=bind,source={source},target={target},readonly']
    if output is not None:
        command += ['--mount', f'type=bind,source={output},target=/platform']
    command += [IMAGE, '/tests/calibrate_platform.py']
    if cache_key:
        command.append('--cache-key')
    try:
        result = subprocess.run(command, check=True, text=True,
                                stdout=subprocess.PIPE if cache_key else None,
                                timeout=120 if cache_key else 86400)
        return result.stdout.strip() if cache_key else None
    finally:
        # Cancellation must not leave a costly reference run behind.
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, timeout=30)


def output_files(directory):
    return sorted(path for name in ('public', 'validation', 'private')
                  for path in (directory / name).rglob('*') if path.is_file())


def valid_cache(directory, key):
    try:
        receipt = json.loads((directory / 'complete.json').read_text())
        limits = json.loads((directory / 'public/limits.json').read_text())
        if receipt['key'] != key or limits['preparation_key'] != key:
            return False
        records = receipt['files']
        if not records or {e['path'] for e in records} != {p.relative_to(directory).as_posix() for p in output_files(directory)}:
            return False
        for entry in records:
            path = directory / entry['path']
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                return False
            if path.stat().st_size != entry['size_bytes'] or digest(path) != entry['sha256']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def prepare(root, cpus):
    prepare_inputs(root)
    parent = root / 'tests/platform'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (parent / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        subprocess.run(['docker', 'build', '-t', IMAGE, str(root / 'tests')], check=True, timeout=1800)
        key = container(root, cpus, cache_key=True)
        if not re.fullmatch(r'[0-9a-f]{64}', key):
            raise RuntimeError('Invalid platform cache key')
        destination = parent / key
        if valid_cache(destination, key):
            print(f'Reusing verified platform calibration: {destination}', flush=True)
            return destination
        print('No matching calibration is cached. Measuring the exact reference and PQ baseline once each per collection. The coding agent has not started.', flush=True)
        staging = Path(tempfile.mkdtemp(prefix='.preparing-', dir=parent))
        container(root, cpus, output=staging)
        limits = json.loads((staging / 'public/limits.json').read_text())
        if limits.get('preparation_key') != key:
            raise RuntimeError('Platform or inputs changed during preparation')
        records = [{'path': p.relative_to(staging).as_posix(), 'size_bytes': p.stat().st_size,
                    'sha256': digest(p)} for p in output_files(staging)]
        (staging / 'complete.json').write_text(json.dumps({'key': key, 'files': records}, indent=2) + '\n')
        if not valid_cache(staging, key):
            raise RuntimeError('Prepared outputs failed verification')
        if destination.exists():
            destination.rename(parent / ('.invalid-' + uuid.uuid4().hex))
        staging.rename(destination)
        print(f'Platform calibration is ready: {destination}', flush=True)
        return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-json', type=Path, required=True)
    parser.add_argument('--cpu-set')
    args = parser.parse_args()
    cpus = cpu_set(args.cpu_set or os.environ.get(CPU_VARIABLE))
    path = prepare(ROOT, cpus)
    args.result_json.write_text(json.dumps({'environment': {
        CPU_VARIABLE: cpus, PLATFORM_VARIABLE: str(path)}}) + '\n')


if __name__ == '__main__':
    def cancel(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancel)
    main()
