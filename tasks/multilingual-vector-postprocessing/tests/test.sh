#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
chmod 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"retrieval_improvement":0,"integrity":0,"reward":0}\n' > /logs/verifier/reward.json
/opt/conda/bin/python -I /task/runtime/restore_submission.py > /logs/verifier/restore.stdout.log 2> /logs/verifier/restore.stderr.log
cleanup() { pkill -KILL -u 10001 2>/dev/null || true; }
trap 'cleanup; exit 143' TERM INT HUP
/usr/bin/timeout --signal=TERM --kill-after=15s 9000s /opt/conda/bin/python -I /tests/grade.py > /logs/verifier/grader.stdout.log 2> /logs/verifier/grader.stderr.log
primary_status=$?
cleanup
printf '%s\n' "$primary_status" > /logs/verifier/primary-exit-status.txt
/usr/bin/timeout --signal=TERM --kill-after=15s 1200s /opt/conda/bin/python -I /tests/rewardkit_deepseek.py /audit --workspace /app --output /logs/verifier/judge.json --max-concurrent-agent 1 --judge deepseek-codex --model deepseek/deepseek-v4.1-flash > /logs/verifier/judge.stdout.log 2> /logs/verifier/judge.stderr.log
judge_status=$?
JUDGE_STATUS="$judge_status" /usr/bin/timeout --kill-after=5s 30s /opt/conda/bin/python -I /tests/finalize.py
