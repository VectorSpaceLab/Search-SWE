#!/usr/bin/env bash
set -uo pipefail
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1 LITELLM_LOCAL_MODEL_COST_MAP=True
pkill -KILL -u 10001 2>/dev/null || true
pkill -KILL -u 10002 2>/dev/null || true
chown root:root /tests /logs/agent /logs/verifier
chmod 700 /tests /logs/agent /logs/verifier
chmod -R go-rwx /tests
cd /tests
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
rm -f /logs/verifier/rewardkit.json /logs/verifier/reward-details.json /logs/verifier/gate-status.json
timeout --kill-after=10 3600 /opt/conda/bin/python -I /tests/grader.py
grader_status=$?
pkill -KILL -u 10001 2>/dev/null || true
judge_status=1
if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
    chmod 600 /logs/agent/trajectory.json
    timeout --kill-after=10 1500 /opt/conda/bin/python -I /tests/run_rewardkit.py > /logs/verifier/judge.stdout 2> /logs/verifier/judge.stderr
    judge_status=$?
fi
pkill -KILL -u 10002 2>/dev/null || true
SEARCH_SWE_JUDGE_STATUS="$judge_status" /opt/conda/bin/python -I /tests/finalize_reward.py
final_status=$?
if (( grader_status || final_status )); then exit 1; fi
