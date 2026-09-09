#!/usr/bin/env bash
set -u

TASK_ID=task-1-1
REWARD_DIR=/logs/verifier
RESULTS_DIR=$REWARD_DIR/${TASK_ID}-eval
REWARD_FILE=$REWARD_DIR/reward.txt
REWARD_JSON=$REWARD_DIR/reward.json
DETAILS_JSON=$REWARD_DIR/reward-details.json
PRIVATE_DIR=$REWARD_DIR/.private
CODEX_HOME_DIR=$PRIVATE_DIR/codex-home
current_phase=initialization

mkdir -p /logs
install -d -o root -g root -m 0700 "$REWARD_DIR"
install -d -o root -g root -m 0700 "$RESULTS_DIR"
install -d -o root -g root -m 0700 "$PRIVATE_DIR" "$CODEX_HOME_DIR"
printf '0\n' > "$REWARD_FILE"
rm -f "$REWARD_JSON" "$DETAILS_JSON" "$RESULTS_DIR/evaluation.json"
/usr/bin/jq -n '{accuracy_at_3: 0.0, jailbreak_judge: 0.0, reward: 0.0}' > "$REWARD_JSON"

# Keep verifier-owned logs and global writable locations outside the
# submission's control.  In particular, the trajectory is an input to the
# root-side jailbreak judge and must not be replaceable by build.sh/run.sh.
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi
for writable_root in /tmp /var/tmp /run/lock; do
    if [[ -d "$writable_root" && ! -L "$writable_root" ]]; then
        chown root:root "$writable_root"
        chmod 0755 "$writable_root"
    fi
done
if [[ -d /home/submission && ! -L /home/submission ]]; then
    chown -R root:root /home/submission
    chmod 0755 /home/submission
fi

execution_error=
if [[ -d /app && ! -L /app ]]; then
    chown -R root:submission /app
    find /app -type d -exec chmod 0550 {} +
    find /app -type f -perm /111 -exec chmod 0550 {} +
    find /app -type f ! -perm /111 -exec chmod 0440 {} +
else
    execution_error="missing or invalid /app directory"
fi

if [[ -d /task && ! -L /task ]]; then
    chown root:root /task
    chmod 0755 /task
fi
if [[ -d /task/data && ! -L /task/data ]]; then
    chown root:root /task/data
    chmod 0755 /task/data
fi
# Corpus and documentation are read-only host mounts. Check access without
# changing host file permissions. Public validation is not mounted here.
if [[ ! -f /task/data/corpus.jsonl || -L /task/data/corpus.jsonl ]] \
    || ! /usr/sbin/runuser -u submission -- test -r /task/data/corpus.jsonl; then
    execution_error="missing, invalid, or unreadable /task/data/corpus.jsonl"
fi
if [[ -d /tests && ! -L /tests ]]; then
    chown root:root /tests
    chmod 0700 /tests
fi
if [[ -d /tests/data && ! -L /tests/data ]]; then
    chown -R root:root /tests/data
    chmod 0700 /tests/data
    find /tests/data -type f -exec chmod 0600 {} +
fi

if [[ -n "$execution_error" ]]; then
    echo "$execution_error" > "$RESULTS_DIR/setup.error.log"
fi

cleanup_submission_processes() {
    /usr/bin/pkill -TERM -u submission 2>/dev/null || true
    sleep 0.5
    /usr/bin/pkill -KILL -u submission 2>/dev/null || true
}

write_zero_reward() {
    printf '0\n' > "$REWARD_FILE"
    /usr/bin/jq -n '{accuracy_at_3: 0.0, jailbreak_judge: 0.0, reward: 0.0}' > "$REWARD_JSON"
    /usr/bin/jq -n \
        --arg phase "$1" \
        --arg reason "$2" \
        '{timeout_guard: {failed_phase: $phase, failure_reason: $reason, reward: 0.0}}' \
        > "$DETAILS_JSON"
}

handle_signal() {
    cleanup_submission_processes
    write_zero_reward "$current_phase" "supervisor received a termination signal"
    exit 143
}

trap handle_signal TERM
trap handle_signal INT
trap handle_signal HUP
trap cleanup_submission_processes EXIT

current_phase=primary_evaluation
SEARCH_SWE_RESULTS_DIR="$RESULTS_DIR" \
    SEARCH_SWE_EXECUTION_ERROR="$execution_error" \
    /usr/bin/timeout --signal=TERM --kill-after=30s 3000s \
    /opt/conda/bin/python /tests/grader.py
grader_status=$?

current_phase=jailbreak_judge
export CODEX_HOME="$CODEX_HOME_DIR"
judge_status=0
judge_log_out="$RESULTS_DIR/jailbreak-judge.stdout.log"
judge_log_err="$RESULTS_DIR/jailbreak-judge.stderr.log"
install_log="$RESULTS_DIR/rewardkit-install.log"

if [[ ! -x /opt/conda/bin/rewardkit ]]; then
    /opt/conda/bin/python -m pip install --no-cache-dir \
        "harbor-rewardkit==0.1.7" >"$install_log" 2>&1 || judge_status=$?
fi

if (( judge_status == 0 )) && [[ -x /opt/conda/bin/rewardkit ]]; then
    if [[ -z "${OPENAI_BASE_URL:-}" || -z "${OPENAI_API_KEY:-}" ]]; then
        echo "OPENAI_BASE_URL and OPENAI_API_KEY are required for the trajectory judge" \
            > "$judge_log_err"
        judge_status=78
    elif ! command -v codex >/dev/null 2>&1; then
        echo "Codex CLI is missing from the verifier image" > "$judge_log_err"
        judge_status=127
    else
        /opt/conda/bin/python - "$OPENAI_BASE_URL" "$CODEX_HOME/config.toml" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

base_url, config_path = sys.argv[1:]
base_url = base_url.rstrip("/")
parsed = urlsplit(base_url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("OPENAI_BASE_URL must be an absolute HTTP(S) URL")
Path(config_path).write_text(
    "model_provider = \"search_swe_judge\"\n\n"
    "[model_providers.search_swe_judge]\n"
    "name = \"Search-SWE trajectory judge endpoint\"\n"
    f"base_url = {json.dumps(base_url)}\n"
    "wire_api = \"responses\"\n"
    "requires_openai_auth = true\n"
    "supports_websockets = false\n",
    encoding="utf-8",
)
PY
        config_status=$?
        if (( config_status != 0 )); then
            judge_status="$config_status"
        else
            chmod 0600 "$CODEX_HOME/config.toml"
        fi
    fi
fi

if (( judge_status == 0 )); then
    /usr/bin/timeout --signal=TERM --kill-after=30s 1200s \
        /opt/conda/bin/rewardkit \
        /tests \
        --workspace /app \
        --output "$REWARD_JSON" \
        --max-concurrent-agent 1 \
        > "$judge_log_out" 2> "$judge_log_err"
    judge_status=$?
fi

current_phase=finalizer
SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /usr/bin/timeout --signal=TERM --kill-after=30s 60s \
    /opt/conda/bin/python /tests/finalize_reward.py \
    > "$RESULTS_DIR/finalizer.stdout.log" \
    2> "$RESULTS_DIR/finalizer.stderr.log"
finalizer_status=$?

if (( finalizer_status != 0 )); then
    write_zero_reward finalizer "reward finalizer failed"
    exit 1
fi
if (( grader_status != 0 || judge_status != 0 )); then
    exit 1
fi
exit 0
