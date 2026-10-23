#!/usr/bin/env bash
set -eu
# Trusted Python and judge subprocesses must never import submission modules.
# Worker creates a separate clean environment for the submitted program.
unset PYTHONHOME PYTHONSTARTUP
export PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tests
cd /tests
install -d -m 0700 /logs /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
cleanup() {
    pkill -KILL -u 10001 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
cleanup
chmod 0700 /tests
if [[ -d /logs/agent ]]; then chmod 0700 /logs/agent; fi
for path in /tmp /var/tmp /dev/shm /run/lock /home/submission; do
    if [[ -d "$path" && ! -L "$path" ]]; then
        # Existing skeleton files must not provide writable storage outside /work.
        chown -Rh root:root "$path"
        chmod -R go-w "$path"
        chmod 0755 "$path"
    fi
done
install -d -m 0755 /work
/opt/conda/bin/python - <<'PY'
import os
from pathlib import Path
p = Path('/app')
if not p.is_dir() or p.is_symlink():
    raise RuntimeError('Invalid submission directory')
for item in [p, *p.rglob('*')]:
    if item.is_symlink():
        raise RuntimeError('Submission artifacts must be regular files/directories, not symlinks')
    os.chown(item, 0, 10001)
    item.chmod(0o550 if item.is_dir() or item.stat().st_mode & 0o111 else 0o440)
PY
status=0
/opt/conda/bin/python /tests/grader.py > /logs/verifier/grader.stdout 2> /logs/verifier/grader.stderr || status=$?
cleanup
if (( status != 0 )); then exit "$status"; fi
test -n "${OPENAI_BASE_URL:-}"
test -n "${OPENAI_API_KEY:-}"
test -s /logs/agent/trajectory.json
judge_status=0
timeout --signal=TERM --kill-after=20s 1900s /opt/conda/bin/python /tests/rewardkit_deepseek.py \
    /tests --workspace /app --output /logs/verifier/audit.json \
    --max-concurrent-agent 1 --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
    > /logs/verifier/judge.stdout 2> /logs/verifier/judge.stderr || judge_status=$?
JUDGE_STATUS="$judge_status" /opt/conda/bin/python /tests/finalize.py
exit "$judge_status"
