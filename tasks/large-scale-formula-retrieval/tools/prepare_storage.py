#!/usr/bin/env python3
"""Prepare job-specific build/development and compact serving filesystems.

This prepares storage only: it never launches, wraps, monitors or schedules an
evaluation. Run as root on the Linux Docker host; no system package is installed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

PACKAGES = [
    ('libfuse2', 'https://deb.debian.org/debian/pool/main/f/fuse/libfuse2_2.9.9-6+b1_amd64.deb',
     'df32b8f65d819f854e096896890d6ad632b6e520977bb120bb3143b4c66e2fcd'),
    ('fuse2fs', 'https://deb.debian.org/debian/pool/main/e/e2fsprogs/fuse2fs_1.47.0-2+b2_amd64.deb',
     '1b3b1e4dad7c409842464871ee61dc978d1c7a19dfa7f42b682fca9b62ccadb4'),
]


def prepare_tools(task):
    cache = task / 'data/runtime-tools'
    cache.mkdir(parents=True, exist_ok=True)
    record = cache / 'verified-runtime.json'
    package_hashes = [expected for _, _, expected in PACKAGES]
    if record.exists():
        saved = json.loads(record.read_text())
        if saved['package_hashes'] != package_hashes or any(
                not (cache / name).is_file() or (cache / name).is_symlink()
                or hashlib.sha256((cache / name).read_bytes()).hexdigest() != expected
                for name, expected in saved['files'].items()):
            raise RuntimeError('Cached storage tools changed; unmount existing runs before rebuilding this cache')
        return cache  # Never overwrite binaries used by another live filesystem.
    for name, url, expected in PACKAGES:
        archive = cache / (name + '.deb')
        if not archive.exists():
            temporary = archive.with_suffix('.part')
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as dest:
                shutil.copyfileobj(source, dest)
            temporary.replace(archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Runtime package integrity failure: {archive}')
        subprocess.run(['dpkg-deb', '-x', str(archive), str(cache)], check=True)
    # The repository's package validator also inspects ignored data directories.
    # Materialize package-local library links as ordinary files.
    for path in cache.rglob('*'):
        if path.is_symlink():
            source = path.resolve()
            if not source.is_relative_to(cache.resolve()) or not source.is_file():
                raise RuntimeError('Unexpected runtime package symlink')
            payload, mode = source.read_bytes(), source.stat().st_mode & 0o777
            path.unlink()
            path.write_bytes(payload)
            path.chmod(mode)
    names = ['fuse2fs.deb', 'libfuse2.deb', 'usr/bin/fuse2fs',
             'lib/x86_64-linux-gnu/libfuse.so.2', 'lib/x86_64-linux-gnu/libulockmgr.so.1']
    record.write_text(json.dumps({'package_hashes': package_hashes,
                                 'files': {name: hashlib.sha256((cache / name).read_bytes()).hexdigest()
                                           for name in names}}, indent=2) + '\n')
    return cache


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--task-root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--runtime-root', type=Path,
                    help='External run-storage parent; defaults to repository jobs/.task-storage/TASK')
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--unmount', action='store_true', help='Unmount this completed run; keep backing images for review')
    ap.add_argument('--probe-mib', type=int, help='Author-only small-capacity ENOSPC probe; cannot be used for evaluation')
    args = ap.parse_args()
    if os.getuid() != 0 or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', args.run_id):
        raise ValueError('Use host root and a simple unique run ID')
    task = args.task_root.resolve()
    runtime_root = (args.runtime_root or task.parents[1] / 'jobs/.task-storage' / task.name).resolve()
    # Harbor hashes the complete task tree, including ignored files. Never put
    # large sparse images or mutable run output inside that content snapshot.
    if runtime_root == task or runtime_root.is_relative_to(task):
        raise ValueError('Runtime storage must be outside the task directory')
    runtime = runtime_root / args.run_id
    if args.unmount:
        config = json.loads((runtime / 'storage.json').read_text())
        if config['run_id'] != args.run_id:
            raise RuntimeError('Storage identity mismatch')
        for phase in ['agent', 'verifier', 'serve']:
            mount = runtime / phase
            if os.path.ismount(mount):
                subprocess.run(['umount', str(mount)], check=True, timeout=30)
        print(f'Unmounted {runtime}; images retained')
        return
    if runtime.exists():
        raise RuntimeError('Run storage already exists; use a fresh run ID')
    if not Path('/dev/fuse').exists() or not shutil.which('mkfs.ext4'):
        raise RuntimeError('Linux host requires /dev/fuse and mkfs.ext4')
    cache = prepare_tools(task)
    fixed = sum(max(p.stat().st_size, p.stat().st_blocks * 512)
                for p in (task / 'data/public').rglob('*') if p.is_file())
    serving_size = 40 << 20
    size = ((64 << 30) - fixed - (512 << 20) - serving_size) // 4096 * 4096
    if args.probe_mib:
        size = args.probe_mib << 20
    if size < 64 << 20:
        raise RuntimeError('Insufficient capacity')
    runtime.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    (runtime / 'evidence').mkdir(mode=0o700)
    config = {'run_id': args.run_id, 'image_capacity_bytes': size,
              'public_bytes': fixed, 'limit_bytes': 64 << 30,
              'diagnostic_reserve_bytes': 512 << 20, 'serving_capacity_bytes': serving_size,
              'prepared_artifact_limit_bytes': 34 << 20,
              'probe': args.probe_mib is not None}
    (runtime / 'storage.json').write_text(json.dumps(config, indent=2) + '\n')
    mounted = []
    try:
        for phase in ['agent', 'verifier', 'serve']:
            image, mount = runtime / (phase + '.img'), runtime / phase
            mount.mkdir(mode=0o755)
            with image.open('xb') as stream:
                stream.truncate(serving_size if phase == 'serve' else size)
            image.chmod(0o600)
            command = ['mkfs.ext4', '-q', '-F', '-b', '4096', '-m', '0.01', '-O', '^has_journal']
            if phase == 'serve':
                command += ['-N', '4096']
            subprocess.run([*command, str(image)], check=True, timeout=120)
            environment = dict(os.environ)
            environment['LD_LIBRARY_PATH'] = str(cache / 'lib/x86_64-linux-gnu')
            subprocess.run([str(cache / 'usr/bin/fuse2fs'), '-o', 'rw,allow_other,default_permissions',
                            str(image), str(mount)], env=environment, check=True, timeout=30)
            if not os.path.ismount(mount):
                raise RuntimeError('Expected FUSE filesystem mount')
            mounted.append(mount)
            mount.chmod(0o755)
            marker = mount / '.storage.json'
            marker.write_text(json.dumps(config) + '\n')
            marker.chmod(0o600)
            if phase == 'agent':
                for name in ['app', 'tmp', 'var-tmp', 'home', 'shm', 'lock', 'diagnostics']:
                    child = mount / name
                    child.mkdir(mode=0o700)
                    os.chown(child, 10001, 10001)
        print(f'FORMULA_STORAGE_ROOT={runtime}')
    except BaseException:
        for mount in reversed(mounted):
            subprocess.run(['umount', str(mount)], check=True, timeout=30)
        raise


if __name__ == '__main__':
    main()
