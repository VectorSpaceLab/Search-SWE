#!/usr/bin/env bash
set -uo pipefail

TASK_ID=task-2-2
EVALUATION_TIMEOUT_SECONDS=3600
JUDGE_TIMEOUT_SECONDS=1200
FINALIZER_TIMEOUT_SECONDS=60
KILL_AFTER_SECONDS=30

REWARD_DIR=/logs/verifier
REWARD_FILE=$REWARD_DIR/reward.txt
REWARD_JSON=$REWARD_DIR/reward.json
DETAILS_JSON=$REWARD_DIR/reward-details.json
LOG_DIR=$REWARD_DIR/$TASK_ID-eval
EVALUATION_REPORT=$LOG_DIR/evaluation.json
VERIFIER_PRIVATE_DIR=$REWARD_DIR/.private
CODEX_HOME_DIR=$VERIFIER_PRIVATE_DIR/codex-home
current_phase=initialization

atomic_zero_text() {
    local temporary=$REWARD_DIR/.reward.txt.$$
    printf '0\n' > "$temporary" && mv -f "$temporary" "$REWARD_FILE"
}

initialize_reward() {
    mkdir -p "$REWARD_DIR"
    atomic_zero_text
    rm -f "$REWARD_JSON" "$DETAILS_JSON"
    local temporary=$REWARD_DIR/.reward.json.$$
    /usr/bin/jq -n \
        '{
            retrieval_improvement: 0.0,
            jailbreak_judge: 0.0,
            reward: 0.0
        }' \
        > "$temporary" &&
        mv -f "$temporary" "$REWARD_JSON"
}

write_zero_reward() {
    local phase=$1
    local reason=$2
    local status=$3
    mkdir -p "$REWARD_DIR"
    atomic_zero_text || true

    local reward_temporary=$REWARD_DIR/.reward.json.$$
    /usr/bin/jq -n \
        '{
            retrieval_improvement: 0.0,
            jailbreak_judge: 0.0,
            reward: 0.0
        }' > "$reward_temporary" &&
        mv -f "$reward_temporary" "$REWARD_JSON"

    local details_temporary=$REWARD_DIR/.reward-details.json.$$
    /usr/bin/jq -n \
        --arg phase "$phase" \
        --arg reason "$reason" \
        --arg status "$status" \
        '{
            timeout_guard: {
                reward: 0.0,
                failed_phase: $phase,
                failure_reason: $reason,
                exit_status: $status
            }
        }' > "$details_temporary" &&
        mv -f "$details_temporary" "$DETAILS_JSON"
}

valid_json_object() {
    /opt/conda/bin/python - "$1" <<'PY'
import json
import sys
from pathlib import Path

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (FileNotFoundError, OSError, json.JSONDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(value, dict) else 1)
PY
}

valid_reward() {
    /opt/conda/bin/python - "$REWARD_FILE" "$REWARD_JSON" <<'PY'
import json
import math
import sys
from pathlib import Path

try:
    reward_text = float(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
    reward_json = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)

if not isinstance(reward_json, dict) or not reward_json:
    raise SystemExit(1)
if any(isinstance(value, bool) or not isinstance(value, (int, float))
       for value in reward_json.values()):
    raise SystemExit(1)
if any(not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
       for value in reward_json.values()):
    raise SystemExit(1)
json_reward = float(reward_json.get("reward", float("nan")))
valid = (
    math.isfinite(reward_text)
    and 0.0 <= reward_text <= 1.0
    and math.isclose(reward_text, json_reward, rel_tol=0.0, abs_tol=1e-9)
)
raise SystemExit(0 if valid else 1)
PY
}

cleanup_submission_processes() {
    pkill -TERM -u submission 2>/dev/null || true
    sleep 0.5
    pkill -KILL -u submission 2>/dev/null || true
}

handle_signal() {
    local signal=$1
    cleanup_submission_processes
    write_zero_reward "$current_phase" "supervisor received $signal" "signal"
    exit 143
}

trap 'handle_signal TERM' TERM
trap 'handle_signal INT' INT
trap 'handle_signal HUP' HUP

initialize_reward || {
    mkdir -p "$REWARD_DIR"
    printf '0\n' > "$REWARD_FILE"
}
rm -f "$EVALUATION_REPORT"

current_phase=primary_evaluation
/usr/bin/timeout \
    --signal=TERM \
    --kill-after="${KILL_AFTER_SECONDS}s" \
    "${EVALUATION_TIMEOUT_SECONDS}s" \
    /tests/run_evaluation.sh
evaluation_status=$?

if (( evaluation_status == 124 || evaluation_status == 137 )); then
    cleanup_submission_processes
    write_zero_reward \
        primary_evaluation \
        "task-specific evaluation timed out" \
        "$evaluation_status"
    exit "$evaluation_status"
fi

if (( evaluation_status != 0 )); then
    cleanup_submission_processes
    write_zero_reward \
        primary_evaluation \
        "task-specific evaluation failed" \
        "$evaluation_status"
    exit 1
fi

if ! valid_json_object "$EVALUATION_REPORT"; then
    cleanup_submission_processes
    write_zero_reward \
        primary_evaluation \
        "task-specific evaluation did not produce a valid report" \
        "$evaluation_status"
    exit 1
fi

current_phase=jailbreak_judge
install -d -o root -g root -m 0700 "$VERIFIER_PRIVATE_DIR" "$CODEX_HOME_DIR"
export CODEX_HOME="$CODEX_HOME_DIR"

# RewardKit's Codex judge shells out to the Codex CLI. Configure an explicit
# OpenAI-compatible provider so the judge uses the injected endpoint over the
# Responses HTTP API rather than falling back to Codex's default provider.
rm -f "$CODEX_HOME/config.toml"
judge_status=0
if [[ -z "${OPENAI_BASE_URL:-}" ]]; then
    printf '%s\n' 'OPENAI_BASE_URL is required for the Codex judge' \
        > "$LOG_DIR/jailbreak-judge.stderr.log"
    judge_status=78
elif [[ -z "${OPENAI_API_KEY:-}" ]]; then
    printf '%s\n' 'OPENAI_API_KEY is required for the Codex judge' \
        > "$LOG_DIR/jailbreak-judge.stderr.log"
    judge_status=78
elif ! command -v codex >/dev/null 2>&1; then
    printf '%s\n' 'Codex CLI is missing from the verifier image' \
        > "$LOG_DIR/jailbreak-judge.stderr.log"
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
    "name = \"Search-SWE judge endpoint\"\n"
    f"base_url = {json.dumps(base_url)}\n"
    "wire_api = \"responses\"\n"
    "requires_openai_auth = true\n"
    "supports_websockets = false\n",
    encoding="utf-8",
)
PY
    config_status=$?
    if (( config_status != 0 )); then
        printf 'Failed to configure the Codex judge provider (status %s)\n' \
            "$config_status" > "$LOG_DIR/jailbreak-judge.stderr.log"
        judge_status="$config_status"
    else
        chmod 0600 "$CODEX_HOME/config.toml"
    fi
fi

if (( judge_status == 0 )); then
    /usr/bin/timeout \
        --signal=TERM \
        --kill-after="${KILL_AFTER_SECONDS}s" \
        "${JUDGE_TIMEOUT_SECONDS}s" \
        /opt/conda/bin/rewardkit \
            /tests \
            --workspace /app \
            --output "$REWARD_JSON" \
            --max-concurrent-agent 1 \
            > "$LOG_DIR/jailbreak-judge.stdout.log" \
            2> "$LOG_DIR/jailbreak-judge.stderr.log"
    judge_status=$?
fi

if (( judge_status != 0 )); then
    write_zero_reward \
        jailbreak_judge \
        "jailbreak judge failed or timed out" \
        "$judge_status"
fi

current_phase=finalizer
SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /usr/bin/timeout \
    --signal=TERM \
    --kill-after="${KILL_AFTER_SECONDS}s" \
    "${FINALIZER_TIMEOUT_SECONDS}s" \
    /opt/conda/bin/python /tests/finalize_reward.py \
        > "$LOG_DIR/finalizer.stdout.log" \
        2> "$LOG_DIR/finalizer.stderr.log"
finalizer_status=$?

if (( finalizer_status != 0 )); then
    write_zero_reward \
        finalizer \
        "reward finalizer failed or timed out" \
        "$finalizer_status"
    exit 1
fi

if ! valid_reward; then
    write_zero_reward \
        finalizer \
        "reward file is missing or invalid" \
        "invalid_reward"
    exit 1
fi

current_phase=complete
if (( judge_status != 0 )); then
    exit 1
fi
exit 0
