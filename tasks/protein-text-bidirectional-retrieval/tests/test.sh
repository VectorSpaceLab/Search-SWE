#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
chmod 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"retrieval_improvement":0,"integrity":0,"reward":0}\n' > /logs/verifier/reward.json
cleanup() { pkill -KILL -u 10001 2>/dev/null || true; }
trap 'cleanup; exit 143' TERM INT HUP
/usr/bin/timeout --signal=TERM --kill-after=15s 128000s \
    /opt/conda/bin/python /tests/grade.py \
    > /logs/verifier/grader.stdout.log 2> /logs/verifier/grader.stderr.log
status=$?
cleanup
if (( status != 0 )); then
    printf '%s\n' "primary evaluator failed with status $status" > /logs/verifier/status.txt
    exit "$status"
fi
/usr/bin/timeout --signal=TERM --kill-after=15s 1200s \
    /opt/conda/bin/python /tests/rewardkit_deepseek.py /audit \
    --workspace /app --output /logs/verifier/judge.json --max-concurrent-agent 1 \
    --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
    > /logs/verifier/judge.stdout.log 2> /logs/verifier/judge.stderr.log
judge_status=$?
JUDGE_STATUS="$judge_status" /usr/bin/timeout --kill-after=5s 30s \
    /opt/conda/bin/python /tests/finalize.py
