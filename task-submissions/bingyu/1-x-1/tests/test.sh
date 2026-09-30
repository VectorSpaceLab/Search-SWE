#!/usr/bin/env bash
set -u

REWARD_DIR=/logs/verifier
RESULTS_DIR=$REWARD_DIR/task-1-x-1-eval
PRIVATE_DIR=$REWARD_DIR/.private
JUDGE_HOME=$PRIVATE_DIR/codex-home
current_phase=initialization

install -d -o root -g root -m 0700 "$REWARD_DIR" "$RESULTS_DIR" "$PRIVATE_DIR" "$JUDGE_HOME"
write_zero_reward() {
    printf '0\n' > "$REWARD_DIR/reward.txt"
    printf '{"filtered_top10":0.0,"jailbreak_judge":0.0,"reward":0.0}\n' > "$REWARD_DIR/reward.json"
}
write_zero_reward
rm -f "$REWARD_DIR/reward-details.json" "$RESULTS_DIR/evaluation.json"

cleanup() {
    pkill -KILL -u submission 2>/dev/null || true
}
interrupted() {
    cleanup
    write_zero_reward
    printf '%s\n' "Interrupted during $current_phase" > "$RESULTS_DIR/interrupted.log"
    exit 143
}
trap cleanup EXIT
trap interrupted INT TERM HUP
cleanup

# Fixed corpus/docs mounts are read-only; never chmod or chown their contents.
if [[ ! -d /app || -L /app ]]; then
    printf 'Missing or invalid /app\n' > "$RESULTS_DIR/setup.error.log"
    exit 1
fi
chown -R root:submission /app
find /app -type d -exec chmod 0550 {} +
find /app -type f -perm /111 -exec chmod 0550 {} +
find /app -type f ! -perm /111 -exec chmod 0440 {} +
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi
for directory in /tmp /var/tmp /run/lock /home/submission; do
    if [[ -d "$directory" && ! -L "$directory" ]]; then
        chown root:root "$directory"
        chmod 0755 "$directory"
    fi
done

current_phase=retrieval
/usr/bin/timeout --signal=TERM --kill-after=30s 3900s \
    /opt/conda/bin/python /tests/grader.py --run-as submission \
    --report "$RESULTS_DIR/evaluation.json"
grader_status=$?
cleanup

# Only this root-side audit may contact the model endpoint. The grader passes
# neither credentials nor proxies to submissions and blocks Internet sockets.
current_phase=jailbreak_judge
judge_status=0
if [[ ! -x /opt/conda/bin/rewardkit ]]; then
    printf '%s\n' 'Missing pinned rewardkit dependency; rebuild the verifier image.' \
        > "$RESULTS_DIR/judge-config.stderr.log"
    judge_status=78
fi
if (( judge_status == 0 )); then
    /opt/conda/bin/python /tests/configure_trajectory_judge.py \
        --template /tests/jailbreak_judge/codex.toml \
        --output "$PRIVATE_DIR/criteria" --home "$JUDGE_HOME" \
        > "$RESULTS_DIR/judge-config.stdout.log" \
        2> "$RESULTS_DIR/judge-config.stderr.log" || judge_status=$?
fi
if (( judge_status == 0 )); then
    CODEX_HOME="$JUDGE_HOME" \
        /usr/bin/timeout --signal=TERM --kill-after=30s 1260s \
        /opt/conda/bin/rewardkit "$PRIVATE_DIR/criteria" \
        --workspace /app --output "$REWARD_DIR/reward.json" --max-concurrent-agent 1 \
        > "$RESULTS_DIR/jailbreak-judge.stdout.log" \
        2> "$RESULTS_DIR/jailbreak-judge.stderr.log" || judge_status=$?
fi

current_phase=finalizer
SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /usr/bin/timeout --signal=TERM --kill-after=10s 60s \
    /opt/conda/bin/python /tests/finalize_reward.py \
    > "$RESULTS_DIR/finalizer.stdout.log" 2> "$RESULTS_DIR/finalizer.stderr.log"
finalizer_status=$?
if (( finalizer_status != 0 )); then
    write_zero_reward
    exit 1
fi
if (( grader_status != 0 || judge_status != 0 )); then
    exit 1
fi
