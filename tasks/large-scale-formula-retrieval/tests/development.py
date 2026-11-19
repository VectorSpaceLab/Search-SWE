"""Check private development memory evidence.

Harbor enforces the agent deadline and collects the available submission for
verification. An interrupted agent command does not invalidate that submission;
its build, serving and retrieval behavior are checked by the grader.
"""
import json
from pathlib import Path

from cgroup_resources import CgroupError
import v1_oom


def check_development(evidence=Path('/task-evidence')):
    try:
        if evidence.stat().st_mode & 0o077:
            raise CgroupError('Development evidence must be private to the host/verifier owner')
        record = json.loads((evidence / 'agent.json').read_text())
        if not isinstance(record, dict):
            raise ValueError('expected a JSON object')
    except (OSError, ValueError) as exc:
        raise CgroupError(f'Cannot read development memory evidence: {exc}') from exc
    if 'cgroup_v1_memory' in record:
        if 'memory_events' in record:
            raise CgroupError('Conflicting development memory evidence for v1 and v2')
        exceeded = v1_oom.violation(record['cgroup_v1_memory'], include_kills=True)
        return record, 'development memory limit' if exceeded else None
    raw = record.get('memory_events')
    if not isinstance(raw, str):
        raise CgroupError('Development evidence must include memory_events')
    events = {}
    try:
        for line in raw.splitlines():
            key, value = line.split()
            count = int(value)
            if key in events or count < 0:
                raise ValueError(f'duplicate or negative {key} counter')
            events[key] = count
        exceeded = events['oom'] > 0
        killed = events['oom_kill'] > 0
    except (KeyError, ValueError) as exc:
        raise CgroupError(f'Invalid development memory events: {exc}') from exc
    return record, 'development memory limit' if exceeded or killed else None
