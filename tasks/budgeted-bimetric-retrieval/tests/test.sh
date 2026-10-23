#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
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
/opt/conda/bin/python /tests/grader.py
