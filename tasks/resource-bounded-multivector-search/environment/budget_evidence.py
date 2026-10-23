"""Native Harbor healthcheck/collect hooks for bounded logs and trusted evidence.

No launch, background monitor or model wrapper: these are two synchronous
filesystem setup/snapshot operations run by Harbor as root.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def setup():
    bounded = Path(os.environ['MULTIVECTOR_DIAGNOSTICS'])
    assert bounded.is_dir() and os.stat(bounded).st_dev == os.stat('/app').st_dev
    os.chown(bounded, 0, 0)
    bounded.chmod(0o755)
    logs = Path('/logs/agent')
    Path('/logs').chmod(0o755)
    for path in [logs, Path('/logs/verifier'), Path('/logs/artifacts')]:
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 0, 0)
        path.chmod(0o555)
    for name, directory in [('codex.txt', False), ('sessions', True)]:
        target = bounded / name
        if directory:
            target.mkdir(exist_ok=True)
        else:
            target.touch(exist_ok=True)
        os.chown(target, 10001, 10001)
        target.chmod(0o700 if directory else 0o600)
        link = logs / name
        if link.is_symlink():
            assert link.readlink() == target
        else:
            assert not link.exists(), 'Use a fresh run directory'
            link.symlink_to(target, target_is_directory=directory)
    marker = Path('/task-evidence/initialized')
    if not marker.exists():
        marker.write_text(json.dumps({'start_monotonic': time.monotonic()}) + '\n')


def collect():
    started = json.loads(Path('/task-evidence/initialized').read_text())['start_monotonic']
    elapsed = time.monotonic() - started
    # Stop any leftover solver/background jobs before snapshotting or copying.
    subprocess.run(['pkill', '-KILL', '-u', '10001'], check=False)
    events = Path('/sys/fs/cgroup/memory.events').read_text()
    evidence = {'development_elapsed_seconds': elapsed, 'memory_events': events,
                'cgroup_memory_peak_bytes': int(Path('/sys/fs/cgroup/memory.peak').read_text())}
    assert Path('/task-evidence/initialized').is_file()
    bounded = Path(os.environ['MULTIVECTOR_DIAGNOSTICS'])
    for name in ['codex.txt', 'sessions']:
        destination = Path('/logs/agent') / name
        assert destination.is_symlink() and destination.readlink() == bounded / name
        destination.unlink()
        source = bounded / name
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copyfile(source, destination)
    # The copied logs are host-owned archival output after development ends.
    Path('/task-evidence/agent.json').write_text(json.dumps(evidence) + '\n')


if __name__ == '__main__':
    {'setup': setup, 'collect': collect}[sys.argv[1]]()
