#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
rm -f /logs/verifier/reward-details.json /logs/verifier/audit.json /logs/verifier/audit-status.json /logs/verifier/evaluation.json
/opt/conda/bin/python /tests/integrity_gate.py prepare
# Deny every general-purpose writable path; indexes/caches live on the quota volume.
chmod 755 /tmp /var/tmp /dev/shm /run/lock
chown root:root /home/submission
chmod 700 /home/submission
chmod 700 /task/private
if [ -d /logs/agent ]; then chmod 700 /logs/agent; fi
/opt/conda/bin/python - <<'LOCK'
import os
from pathlib import Path
for base, dirs, files in os.walk('/app', followlinks=False):
    path=Path(base)
    os.chown(path,0,0); path.chmod(0o755)
    for name in files:
        p=path/name
        if p.is_symlink(): continue
        executable=bool(p.stat().st_mode & 0o111)
        os.chown(p,0,0);p.chmod(0o755 if executable else 0o644)
LOCK
trap 'pkill -KILL -u 10001 2>/dev/null || true' EXIT
trap 'exit 143' INT TERM HUP
primary_status=0
timeout --signal=TERM --kill-after=10s 14400s /opt/conda/bin/python /tests/grader.py || primary_status=$?
/opt/conda/bin/python /tests/integrity_gate.py cleanup
judge_status=78
if [ "$primary_status" -eq 0 ] && [ -n "${OPENAI_API_KEY:-}" ] && [ -n "${OPENAI_BASE_URL:-}" ]; then
    judge_status=0
    timeout --signal=TERM --kill-after=30s 1200s /opt/conda/bin/python /tests/rewardkit_deepseek.py \
        /audit --workspace /app --output /logs/verifier/audit.json \
        --max-concurrent-agent 1 --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
        > /logs/verifier/audit.stdout.log 2> /logs/verifier/audit.stderr.log || judge_status=$?
fi
SEARCH_SWE_PRIMARY_STATUS="$primary_status" SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /opt/conda/bin/python /tests/integrity_gate.py finalize --report evaluation.json
