"""Quota-backed development logs and private, trusted memory evidence."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

MAX_LOG_ARCHIVE_BYTES = 512 << 20  # Existing diagnostic reserve; archival I/O only.


def check_log_budget(source):
    """Bound expansion before privileged copying, including repeated hardlinks."""
    total = 0
    pending = [(source, True)]
    while pending:
        directory, root = pending.pop()
        for entry in directory.iterdir():
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append((entry, False))
                total += 4096
            elif stat.S_ISREG(info.st_mode):
                if root and entry.name == 'trajectory.json' and info.st_uid != 0:
                    continue
                # Each path may be expanded by Docker/tar. Charge logical size
                # for holes and each hardlink, plus blocks and entry overhead.
                size = max(info.st_size, info.st_blocks * 512)
                total += ((size + 4095) // 4096) * 4096 + 4096
            else:
                continue
            total += len(os.fsencode(entry.relative_to(source)))
            if total > MAX_LOG_ARCHIVE_BYTES:
                raise RuntimeError('Agent log archive exceeds the 512 MiB diagnostic reserve; '
                                   'source logs are retained on the bounded filesystem')
    return total


def setup():
    bounded = Path(os.environ['FORMULA_DIAGNOSTICS'])
    assert bounded.is_dir() and os.stat(bounded).st_dev == os.stat('/app').st_dev
    # Sticky ownership protects root-published framework artifacts while each
    # harness can create its own quota-backed log/session names.
    os.chown(bounded, 0, 0)
    bounded.chmod(0o1777)
    logs = Path('/logs/agent')
    Path('/logs').mkdir(exist_ok=True)
    Path('/logs').chmod(0o755)
    for path in [Path('/logs/verifier'), Path('/logs/artifacts')]:
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 0, 0)
        path.chmod(0o555)
    if logs.is_symlink():
        assert logs.readlink() == bounded
    else:
        assert not logs.is_mount(), 'Use the Search-SWE Docker adapter for bounded logs'
        if logs.exists():
            logs.rmdir()  # A fresh environment has no agent log entries yet.
        logs.symlink_to(bounded, target_is_directory=True)
    Path('/task-evidence/initialized').write_text('bounded logs initialized\n')


def copy_logs(source, destination, *, root=True):
    """Snapshot regular files without following solver-controlled links/FIFOs."""
    if root:
        check_log_budget(source)
    for entry in source.iterdir():
        target = destination / entry.name
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            target.mkdir(mode=0o700)
            copy_logs(entry, target, root=False)
        elif stat.S_ISREG(mode):
            if root and entry.name == 'trajectory.json' and entry.lstat().st_uid != 0:
                continue  # The framework publishes the ATIF; retain raw logs.
            # copyfile leaves the new snapshot owned by root; source hard links
            # retain their metadata, including any links into the submission.
            shutil.copyfile(entry, target, follow_symlinks=False)
            target.chmod(0o600)


def stop_solver():
    subprocess.run(['pkill', '-KILL', '-u', '10001'], check=False)
    deadline = time.monotonic() + 10
    while True:
        live = False
        for status in Path('/proc').glob('[0-9]*/status'):
            try:
                fields = dict(line.split(':', 1) for line in status.read_text().splitlines() if ':' in line)
                if fields['Uid'].split()[0] == '10001' and fields['State'].split()[0] != 'Z':
                    live = True
            except (FileNotFoundError, ProcessLookupError):
                pass
        if not live:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Solver processes survived log freeze')
        time.sleep(.01)


def freeze():
    logs, evidence = Path('/logs/agent'), Path('/task-evidence')
    marker = evidence / 'logs-frozen'
    if marker.exists():
        assert logs.is_dir() and not logs.is_symlink()
        return
    assert (evidence / 'initialized').is_file()
    bounded = Path(os.environ['FORMULA_DIAGNOSTICS'])
    assert logs.is_symlink() and logs.readlink() == bounded
    # Stop all solver/background processes before snapshotting their logs.
    stop_solver()
    record = {'memory_events': Path('/sys/fs/cgroup/memory.events').read_text(),
              'cgroup_memory_peak_bytes': int(Path('/sys/fs/cgroup/memory.peak').read_text())}
    os.chown(bounded, 0, 0)
    bounded.chmod(0o500)
    snapshot = Path(tempfile.mkdtemp(prefix='.agent-logs-', dir='/logs'))
    try:
        copy_logs(bounded, snapshot)
        logs.unlink()
        snapshot.rename(logs)
        logs.chmod(0o755)
    finally:
        if snapshot.exists():
            shutil.rmtree(snapshot)
    # Host-side ATIF conversion and upload happen after this snapshot. Root can
    # publish the resulting trajectory here; the stopped solver cannot write it.
    (evidence / 'agent.json').write_text(json.dumps(record) + '\n')
    marker.write_text('bounded logs frozen\n')


def collect():
    # Harbor invokes collection after generating/uploading the ATIF artifact.
    # Keep the memory evidence from the earlier, pre-conversion freeze intact.
    freeze()


if __name__ == '__main__':
    {'setup': setup, 'freeze': freeze, 'collect': collect}[sys.argv[1]]()
