"""Check private memory evidence and Harbor 0.22's host command-completion log.

Harbor enforces the development deadline. An interrupted installed-agent command
has no completion record, even when subsequent credential cleanup succeeds.
Only this host-written file is mounted; the surrounding trial contains secrets.
"""
import json
from pathlib import Path


def check_development(evidence=Path('/task-evidence'), native_log=Path('/task-run/trial.log')):
    if evidence.stat().st_mode & 0o077 or native_log.parent.stat().st_mode & 0o077:
        raise RuntimeError('Development evidence must be private to the host/verifier owner')
    record = json.loads((evidence / 'agent.json').read_text())
    events = dict(line.split() for line in record['memory_events'].splitlines())
    if any(int(events.get(name, '0')) for name in ['oom', 'oom_kill']):
        return record, 'development memory limit'
    lines = native_log.read_text().splitlines()
    try:
        end = lines.index('Collecting main service artifacts')
    except ValueError as exc:
        raise RuntimeError('Missing native agent-phase completion boundary') from exc
    started = sum(line.startswith('Running command: ') for line in lines[:end])
    completed = lines[:end].count('Command outputs captured')
    if not started or completed > started:
        raise RuntimeError('Invalid native installed-agent command evidence')
    record['native_commands_started'] = started
    record['native_commands_completed'] = completed
    if completed < started:
        return record, 'development command incomplete (timeout or agent failure)'
    return record, None
