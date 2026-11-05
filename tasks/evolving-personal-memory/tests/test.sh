#!/usr/bin/env bash
set -u
umask 077
RESULTS_DIR=/logs/verifier/evolving-personal-memory-eval
install -d -o root -g root -m 0700 /logs/verifier "$RESULTS_DIR"
printf '0\n' > /logs/verifier/reward.txt
printf '{"fama":0,"jailbreak_judge":0,"reward":0}\n' > /logs/verifier/reward.json
execution_error=
if [[ ! -f /app/answer.sh || -L /app/answer.sh || ! -x /app/answer.sh ]]; then execution_error='Missing or invalid executable answer.sh'; fi
if [[ -e /app/answer || -L /app/answer ]]; then
 if [[ ! -d /app/answer || -L /app/answer ]]; then execution_error='Invalid answer support directory'; fi
fi
# Allow internal links but reject links resolving outside answer-side code.
if [[ -d /app/answer && ! -L /app/answer ]]; then
 if ! /opt/conda/bin/python - <<'CHECK'
from pathlib import Path
root=Path('/app/answer').resolve()
for p in root.rglob('*'):
    if p.is_symlink():
        try: p.resolve(strict=True).relative_to(root)
        except (ValueError,FileNotFoundError,RuntimeError): raise SystemExit(1)
CHECK
 then execution_error='Answer-side link escapes support directory'; fi
fi
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
# Answer-side code has a separate read-only group; the parent allows traversal.
chmod 0751 /app
if [[ -f /app/answer.sh && ! -L /app/answer.sh ]]; then
 chown root:answer-code /app/answer.sh
 chmod 0550 /app/answer.sh
fi
if [[ -d /app/answer && ! -L /app/answer ]]; then
 chown -R root:answer-code /app/answer
 find /app/answer -type d -exec chmod 0550 {} +
 find /app/answer -type f -perm /111 -exec chmod 0550 {} +
 find /app/answer -type f ! -perm /111 -exec chmod 0440 {} +
fi
cleanup() { for slot in 1 2 3 4 5 6 7 8; do pkill -KILL -u "answer$slot" 2>/dev/null || true; done; pkill -TERM -u submission 2>/dev/null || true; sleep .2; pkill -KILL -u submission 2>/dev/null || true; pkill -TERM -u audit 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 143' INT TERM HUP
SEARCH_SWE_EXECUTION_ERROR="$execution_error" timeout --signal=TERM --kill-after=15s 19500s /opt/conda/bin/python /tests/grader.py
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
 timeout --signal=TERM --kill-after=15s 3600s /opt/conda/bin/python /tests/run_audit.py --runner /tests/judge_repeats.py /tests/rewardkit_deepseek.py --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
  > "$RESULTS_DIR/jailbreak-judge.stdout.log" 2> "$RESULTS_DIR/jailbreak-judge.stderr.log"
 judge_status=$?
fi
cleanup
/opt/conda/bin/python /tests/collect_audit_logs.py
SEARCH_SWE_JUDGE_STATUS="$judge_status" /opt/conda/bin/python /tests/finalize_reward.py
final_status=$?
if (( grader_status != 0 || judge_status != 0 || final_status != 0 )); then exit 1; fi
