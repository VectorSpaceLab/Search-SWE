#!/usr/bin/env bash
set -eu
unset PYTHONHOME PYTHONSTARTUP
export PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 PYTHONPATH=/tests
cd /tests
install -d -m 0700 /logs /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
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
/opt/conda/bin/python /tests/grader.py > /logs/verifier/grader.stdout 2> /logs/verifier/grader.stderr
