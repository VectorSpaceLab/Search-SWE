#!/usr/bin/env bash
set -u
umask 077
RESULTS_DIR=/logs/verifier/financial-report-qa-eval
install -d -o root -g root -m 0700 /logs/verifier "$RESULTS_DIR"
printf '0\n' > /logs/verifier/reward.txt
printf '{"evidence_recall_at_5":0,"jailbreak_judge":0,"reward":0}\n' > /logs/verifier/reward.json
execution_error=
if [[ -d /app && ! -L /app ]]; then
 chown -R root:submission /app
 find /app -type d -exec chmod 0550 {} +
 find /app -type f -perm /111 -exec chmod 0550 {} +
 find /app -type f ! -perm /111 -exec chmod 0440 {} +
else execution_error='Missing or invalid /app'; fi
chown -R root:root /tests
chmod 0700 /tests
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
 chown -R root:root /logs/agent
 chmod 0700 /logs/agent
 if [[ -f /logs/agent/trajectory.json ]]; then chmod 0600 /logs/agent/trajectory.json; fi
fi
for p in /tmp /var/tmp /run/lock; do [[ ! -d "$p" ]] || chmod 0755 "$p"; done
cleanup() { pkill -TERM -u submission 2>/dev/null || true; sleep .2; pkill -KILL -u submission 2>/dev/null || true; pkill -TERM -u audit 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 143' INT TERM HUP
SEARCH_SWE_EXECUTION_ERROR="$execution_error" timeout --signal=TERM --kill-after=15s 9300s /opt/conda/bin/python /tests/grader.py
grader_status=$?
cleanup
judge_status=78
if [[ -n "${OPENAI_API_KEY:-}" && "${OPENAI_BASE_URL%/}" == 'https://openrouter.ai/api/v1' && -f /logs/agent/trajectory.json ]]; then
 # Make a root-owned snapshot. The judge receives no tests, labels, grading files or submission API key.
 install -d -o root -g audit -m 0750 /audit /audit/config /audit/config/jailbreak_judge
 install -d -o audit -g audit -m 0700 /audit/output /home/audit/tmp
 cp -a /app /audit/submission
 chown -R root:audit /audit/submission
 find /audit/submission -type d -exec chmod 0550 {} +
 find /audit/submission -type f -exec chmod 0440 {} +
 install -o root -g audit -m 0440 /logs/agent/trajectory.json /audit/trajectory.json
 install -o root -g audit -m 0440 /tests/jailbreak_judge/codex.toml /audit/config/jailbreak_judge/codex.toml
 timeout --signal=TERM --kill-after=15s 3600s /opt/conda/bin/python /tests/run_audit.py --runner /tests/rewardkit_deepseek.py --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
  > "$RESULTS_DIR/jailbreak-judge.stdout.log" 2> "$RESULTS_DIR/jailbreak-judge.stderr.log"
 judge_status=$?
fi
cleanup
/opt/conda/bin/python /tests/collect_audit_logs.py
SEARCH_SWE_JUDGE_STATUS="$judge_status" /opt/conda/bin/python /tests/finalize_reward.py
final_status=$?
if (( grader_status != 0 || judge_status != 0 || final_status != 0 )); then exit 1; fi
