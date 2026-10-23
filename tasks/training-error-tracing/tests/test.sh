#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
chmod 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"tracing_improvement":0,"jailbreak_judge":0,"reward":0}\n' > /logs/verifier/reward.json
rm -f /logs/verifier/evaluation.json /logs/verifier/reward-details.json

cleanup() {
    pkill -CONT -u submission 2>/dev/null || true
    pkill -TERM -u submission 2>/dev/null || true
    sleep 0.1
    pkill -KILL -u submission 2>/dev/null || true
}
interrupted() {
    cleanup
    printf '0\n' > /logs/verifier/reward.txt
    printf '{"infrastructure_error":true,"reason":"verifier interrupted"}\n' > /logs/verifier/reward-details.json
    exit 143
}
trap interrupted TERM INT HUP

timeout --signal=TERM --kill-after=10s 6900s /opt/conda/bin/python /tests/efficiency_grade.py
primary_status=$?
cleanup

judge_status=78
if [[ -n "${OPENAI_API_KEY:-}" && -n "${OPENAI_BASE_URL:-}" ]]; then
    timeout --signal=TERM --kill-after=30s 1200s \
        /opt/conda/bin/python /tests/rewardkit_deepseek.py \
        /audit --workspace /app --output /logs/verifier/reward.json \
        --max-concurrent-agent 1 --judge deepseek-codex \
        --model deepseek/deepseek-v4.1-flash \
        > /logs/verifier/judge.stdout.log 2> /logs/verifier/judge.stderr.log
    judge_status=$?
else
    printf '%s\n' 'Missing verifier OPENAI_API_KEY or OPENAI_BASE_URL' > /logs/verifier/judge.stderr.log
fi
export SEARCH_SWE_PRIMARY_STATUS=$primary_status
export SEARCH_SWE_JUDGE_STATUS=$judge_status
timeout --signal=TERM --kill-after=5s 60s /opt/conda/bin/python /tests/finalize_reward.py
finalizer_status=$?
if (( finalizer_status != 0 )); then
    printf '0\n' > /logs/verifier/reward.txt
    printf '{"tracing_improvement":0,"jailbreak_judge":0,"reward":0}\n' > /logs/verifier/reward.json
    printf '{"infrastructure_error":true,"reason":"finalizer failed"}\n' > /logs/verifier/reward-details.json
fi
exit 0
