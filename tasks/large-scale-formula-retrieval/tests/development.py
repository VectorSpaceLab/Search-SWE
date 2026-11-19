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
    if evidence.stat().st_mode & 0o077:
        raise RuntimeError('Development evidence must be private to the host/verifier owner')
    record = json.loads((evidence / 'agent.json').read_text())
    if 'cgroup_v1_memory' in record:
        if 'memory_events' in record:
            raise CgroupError('Conflicting development memory evidence for v1 and v2')
        exceeded = v1_oom.violation(record['cgroup_v1_memory'], include_kills=True)
        return record, 'development memory limit' if exceeded else None
    events = dict(line.split() for line in record['memory_events'].splitlines())
    counts = [int(events[name]) for name in ['oom', 'oom_kill']]
    if any(count < 0 for count in counts):
        raise ValueError('Invalid development memory event count')
    if any(counts):
        return record, 'development memory limit'
    return record, None
