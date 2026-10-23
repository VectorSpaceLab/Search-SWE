#!/usr/bin/env bash
set -eu
unset PYTHONHOME PYTHONSTARTUP
export PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tests
cd /tests
install -d -m 0700 /logs /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
rm -f /logs/verifier/audit.json /logs/verifier/audit-status.json /logs/verifier/reward-details.json /logs/verifier/evaluation.json
/opt/conda/bin/python /tests/integrity_gate.py prepare
cleanup() { pkill -KILL -u 10001 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 143' INT TERM
cleanup
chmod 0700 /tests
if [[ -d /logs/agent ]]; then chmod 0700 /logs/agent; fi
for path in /tmp /var/tmp /dev/shm /run/lock /home/submission; do
    if [[ -d "$path" && ! -L "$path" ]]; then
        chown -Rh root:root "$path"
        chmod -R go-w "$path"
        chmod 0755 "$path"
    fi
done
/opt/conda/bin/python - <<'PY'
import os
from pathlib import Path
p = Path('/app')
if not p.is_dir() or p.is_symlink():
    raise RuntimeError('Invalid submission directory')
for item in [p, *p.rglob('*')]:
    if item.is_symlink() or not (item.is_file() or item.is_dir()):
        raise RuntimeError('Submission artifacts must be regular files or directories')
    os.chown(item, 0, 10001)
    item.chmod(0o550 if item.is_dir() or item.stat().st_mode & 0o111 else 0o440)
PY
trap 'exit 143' INT TERM HUP
primary_status=0
timeout --signal=TERM --kill-after=10s 18000s /opt/conda/bin/python /tests/grader.py \
    > /logs/verifier/grader.stdout 2> /logs/verifier/grader.stderr || primary_status=$?
/opt/conda/bin/python /tests/integrity_gate.py cleanup
judge_status=78
if [ "$primary_status" -eq 0 ] && [ -n "${OPENAI_API_KEY:-}" ] && [ -n "${OPENAI_BASE_URL:-}" ]; then
    judge_status=0
    timeout --signal=TERM --kill-after=30s 1200s /opt/conda/bin/python /tests/rewardkit_deepseek.py \
        /audit --workspace /app/submission --output /logs/verifier/audit.json \
        --max-concurrent-agent 1 --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
        > /logs/verifier/audit.stdout.log 2> /logs/verifier/audit.stderr.log || judge_status=$?
fi
SEARCH_SWE_PRIMARY_STATUS="$primary_status" SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /opt/conda/bin/python /tests/integrity_gate.py finalize --report evaluation.json
