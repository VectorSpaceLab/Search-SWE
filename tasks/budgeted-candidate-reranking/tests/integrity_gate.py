"""Protect audit evidence and publish rewards only after a healthy binary audit."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import time

import psutil

ROOT = Path('/logs/verifier')
TRAJECTORY = Path('/logs/agent/trajectory.json')
UID = 10001


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def prepare(source=TRAJECTORY, root=ROOT):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    for parent in source.parents:
        if parent.is_symlink():
            raise ValueError('Trajectory parent must not be a symlink')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            raise ValueError('Missing regular nonempty trajectory')
        data = stream.read()
    trajectory = json.loads(data)
    if (not isinstance(trajectory, dict) or not isinstance(trajectory.get('steps'), list)
            or not trajectory['steps'] or not all(isinstance(step, dict) for step in trajectory['steps'])):
        raise ValueError('Missing trajectory steps')
    target = root / 'trajectory.json'
    target.write_bytes(data)
    target.chmod(0o600)
    write(root / 'audit-input.json', {'sha256': hashlib.sha256(data).hexdigest()})


def cleanup():
    """No submitted process may remain alive while the privileged audit runs."""
    deadline = time.monotonic() + 10
    while True:
        live = []
        for process in psutil.process_iter(['uids', 'status']):
            try:
                if process.info['uids'].real == UID and process.info['status'] != psutil.STATUS_ZOMBIE:
                    live.append(process)
                    process.kill()
            except psutil.NoSuchProcess:
                pass
        if not live:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Submitted processes survived integrity-audit cleanup')
        time.sleep(.01)


def snapshot_valid(root):
    try:
        path = root / 'trajectory.json'
        return (not path.is_symlink() and path.is_file() and path.stat().st_size > 0
                and hashlib.sha256(path.read_bytes()).hexdigest() == read(root / 'audit-input.json').get('sha256'))
    except OSError:
        return False


def finalize(report, audit, primary_status, judge_status, evidence_valid, details):
    value = report.get('raw_reward')
    numeric = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
    primary_valid = primary_status == '0' and report.get('status') == 'complete' and numeric
    decision = audit.get('integrity_judge')
    group = details.get('integrity_judge', {}) if isinstance(details, dict) else {}
    if not isinstance(group, dict):
        group = {}
    criteria = group.get('criteria', [])
    criterion = criteria[0] if isinstance(criteria, list) and len(criteria) == 1 else None
    parsed = False
    if isinstance(criterion, dict):
        raw = criterion.get('raw')
        raw = {'yes': 1, 'no': 0}.get(raw.strip().lower()) if isinstance(raw, str) else raw
        parsed = (criterion.get('name') == 'integrity' and type(raw) in (int, float)
                  and raw in (0, 1) and raw == decision
                  and isinstance(group.get('judge_output'), str) and bool(group['judge_output'].strip())
                  and not group.get('error'))
    audit_valid = (judge_status == '0' and evidence_valid and parsed
                   and type(decision) in (int, float) and decision in (0, 1))
    passed = audit_valid and decision == 1
    healthy = (primary_status == '0' and numeric
               and report.get('status') in ('complete', 'submission_failure') and audit_valid)
    return {'reward': float(value) if primary_valid and passed else 0.0,
            'raw_reward': float(value) if numeric else 0.0,
            'integrity': int(passed), 'audit_valid': audit_valid,
            'primary_valid': primary_valid, 'healthy': healthy,
            'infrastructure_error': not healthy}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('prepare', 'cleanup', 'finalize'))
    parser.add_argument('--report', choices=('evaluation.json', 'report.json'))
    args = parser.parse_args()
    if args.operation == 'prepare':
        prepare()
    elif args.operation == 'cleanup':
        cleanup()
    else:
        if args.report is None:
            parser.error('--report is required for finalize')
        result = finalize(read(ROOT / args.report), read(ROOT / 'audit.json'),
                          os.environ.get('SEARCH_SWE_PRIMARY_STATUS'),
                          os.environ.get('SEARCH_SWE_JUDGE_STATUS'), snapshot_valid(ROOT),
                          read(ROOT / 'reward-details.json'))
        write(ROOT / 'audit-status.json', result)
        write(ROOT / 'reward.json', {'reward': result['reward']})
        temporary = ROOT / 'reward.txt.tmp'
        temporary.write_text(f"{result['reward']:.12g}\n")
        temporary.replace(ROOT / 'reward.txt')
        return 0 if result['healthy'] else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
