#!/usr/bin/env bash
set -euo pipefail
install -d -o root -g root -m 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0.0}\n' > /logs/verifier/reward.json
rm -f /logs/verifier/audit.json /logs/verifier/audit-status.json /logs/verifier/reward-details.json /logs/verifier/report.json
/opt/conda/bin/python /tests/integrity_gate.py prepare
chmod 0700 /tests
unset PYTHONHOME PYTHONSTARTUP
export PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 PYTHONPATH=/task/runtime
cd /tests
trap '/opt/conda/bin/python -c "from isolation import cleanup; cleanup()"' EXIT
/opt/conda/bin/python -c 'from transfer import restore; restore()'
trap 'exit 143' INT TERM HUP
primary_status=0
timeout --signal=TERM --kill-after=10s 4650s /opt/conda/bin/python /task/runtime/evaluate.py --private-dir /task/private --reference-dir /tests/data --output-dir /logs/verifier \
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
    /opt/conda/bin/python /tests/integrity_gate.py finalize --report report.json
