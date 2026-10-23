"""Check root-owned development clock and cgroup evidence."""
import json
import math
from pathlib import Path


def check_development(evidence=Path('/task-evidence')):
    if evidence.stat().st_mode & 0o077:
        raise RuntimeError('Development evidence must be private to the host/verifier owner')
    record = json.loads((evidence / 'agent.json').read_text())
    elapsed = record['development_elapsed_seconds']
    if not isinstance(elapsed, (float, int)) or not math.isfinite(elapsed) or elapsed < 0:
        raise RuntimeError('Invalid development clock')
    if elapsed > 7200:
        return record, 'development timeout'
    events = dict(line.split() for line in record['memory_events'].splitlines())
    if any(int(events.get(name, '0')) for name in ['oom', 'oom_kill']):
        return record, 'development memory limit'
    return record, None
