#!/usr/bin/env bash
set -euo pipefail

REWARD_DIR=/logs/verifier
PRIVATE_DIR=$REWARD_DIR/.private
JUDGE_REWARD=$PRIVATE_DIR/judge-reward.json
install -d -o root -g root -m 0700 "$REWARD_DIR" "$PRIVATE_DIR"
write_zero_reward() {
    printf '0\n' > "$REWARD_DIR/reward.txt"
    printf '{"retrieval_reward":0,"jailbreak_judge":0,"reward":0}\n' > "$REWARD_DIR/reward.json"
}
write_zero_reward
rm -f "$REWARD_DIR/report.json" "$REWARD_DIR/reward-details.json" "$JUDGE_REWARD"

cleanup() {
    /usr/bin/pkill -TERM -u submission 2>/dev/null || true
    sleep 0.1
    /usr/bin/pkill -KILL -u submission 2>/dev/null || true
}
abort() {
    write_zero_reward
    exit 1
}
trap cleanup EXIT
trap abort TERM INT HUP

test -d /app && test ! -L /app
chown -R --no-dereference root:submission /app
find /app -type d -exec chmod 0550 {} +
find /app -type f -perm /111 -exec chmod 0550 {} +
find /app -type f ! -perm /111 -exec chmod 0440 {} +
chmod 0700 /tests
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi
# Each service run gets fresh scratch space. Shared directories cannot preserve
# hidden-query results between the independently timed service instances.
for directory in /tmp /var/tmp /run/lock /home/submission /dev/shm /dev/mqueue; do
    if [[ -d "$directory" && ! -L "$directory" ]]; then
        chown root:root "$directory"
        chmod 0755 "$directory"
    fi
done

cleanup
grader_status=0
/usr/bin/timeout --signal=TERM --kill-after=5s 2300s \
    /opt/conda/bin/python /tests/grader.py || grader_status=$?
cleanup

# Only the root-side judge can use the verifier's OpenRouter access. Candidate
# commands get a fresh environment and a socket filter before dropping UID.
# Write the judge's own score to a private file, never the public reward path.
judge_status=0
if (( grader_status != 0 )); then
    printf '%s\n' 'Audit skipped because retrieval execution failed' > "$REWARD_DIR/jailbreak-judge.stderr.log"
    judge_status=1
elif [[ ! -s /logs/agent/trajectory.json || -L /logs/agent/trajectory.json ]]; then
    printf '%s\n' 'A regular, nonempty agent trajectory is required' > "$REWARD_DIR/jailbreak-judge.stderr.log"
    judge_status=1
elif [[ -z "${OPENAI_BASE_URL:-}" || -z "${OPENAI_API_KEY:-}" ]]; then
    printf '%s\n' 'VERIFIER_OPENAI_BASE_URL and VERIFIER_OPENAI_API_KEY are required for the integrity judge' \
        > "$REWARD_DIR/jailbreak-judge.stderr.log"
    judge_status=78
else
    /usr/bin/timeout --signal=TERM --kill-after=30s 1260s \
        /opt/conda/bin/python /tests/rewardkit_deepseek.py /tests \
        --workspace /app --output "$JUDGE_REWARD" --max-concurrent-agent 1 \
        --judge deepseek-codex --model deepseek/deepseek-v4.1-flash \
        > "$REWARD_DIR/jailbreak-judge.stdout.log" \
        2> "$REWARD_DIR/jailbreak-judge.stderr.log" || judge_status=$?
fi

SEARCH_SWE_GRADER_STATUS="$grader_status" SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /usr/bin/timeout --signal=TERM --kill-after=5s 60s \
    /opt/conda/bin/python /tests/finalize_reward.py \
    > "$REWARD_DIR/finalizer.stdout.log" 2> "$REWARD_DIR/finalizer.stderr.log" || abort

if (( grader_status != 0 || judge_status != 0 )); then
    exit 1
fi
