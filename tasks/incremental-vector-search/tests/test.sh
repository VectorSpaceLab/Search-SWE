#!/usr/bin/env bash
set -eu
install -d -m 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
cleanup() {
    pkill -KILL -u 10001 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' INT TERM
cleanup
/opt/conda/bin/python /tests/grader.py
cleanup
judge_status=0
timeout 3600 /opt/conda/bin/python /tests/rewardkit_deepseek.py /tests \
    --workspace /app/submission --output /logs/verifier/audit.json \
    --max-concurrent-agent 1 --judge deepseek-codex \
    --model deepseek/deepseek-v4.1-flash \
    > /logs/verifier/audit.stdout.log 2> /logs/verifier/audit.stderr.log || judge_status=$?
SEARCH_SWE_JUDGE_STATUS="$judge_status" /opt/conda/bin/python /tests/finalize.py
