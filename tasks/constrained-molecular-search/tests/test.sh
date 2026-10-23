#!/usr/bin/env bash
set -euo pipefail
install -d -o root -g root -m 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0.0}\n' > /logs/verifier/reward.json
chmod 0700 /tests
export PYTHONPATH=/task/runtime
trap '/opt/conda/bin/python -c "from isolation import cleanup; cleanup()"' EXIT
/opt/conda/bin/python -c 'from transfer import restore; restore()'
status=0
/usr/bin/timeout --signal=TERM --kill-after=10s 4650s \
    /opt/conda/bin/python /task/runtime/evaluate.py \
    --private-dir /task/private --reference-dir /tests/data --output-dir /logs/verifier || status=$?
if (( status != 0 )); then
    exit "$status"
fi
/opt/conda/bin/python - <<'PY'
import json, math
from pathlib import Path
root = Path('/logs/verifier')
report = json.loads((root/'report.json').read_text())
value = report.get('reward')
if report.get('valid') is not True or type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
    raise ValueError('Invalid grading result')
(root/'reward.txt').write_text(str(value) + '\n')
(root/'reward.json').write_text(json.dumps({'reward':value}) + '\n')
PY
