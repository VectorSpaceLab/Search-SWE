#!/usr/bin/env bash
set -u

RESULTS_DIR=/logs/artifacts/task-2-5-eval
INDEX_DIR=$RESULTS_DIR/index
OUTPUT_PATH=$RESULTS_DIR/results.jsonl
BUILD_METRICS=$RESULTS_DIR/build.metrics.json
RUN_METRICS=$RESULTS_DIR/run.metrics.json
BASELINE_INDEX_DIR=$RESULTS_DIR/starter-index
BASELINE_OUTPUT_PATH=$RESULTS_DIR/starter-results.jsonl
BASELINE_BUILD_METRICS=$RESULTS_DIR/starter-build.metrics.json
BASELINE_RUN_METRICS=$RESULTS_DIR/starter-run.metrics.json
BASELINE_ROOT=/baseline-starter
REPORT_PATH=/logs/verifier/report.json
REWARD_PATH=/logs/verifier/reward.txt
BUILD_TIMEOUT_SECONDS=3600
RUN_TIMEOUT_SECONDS=900
BASELINE_BUILD_TIMEOUT_SECONDS=1800
BASELINE_RUN_TIMEOUT_SECONDS=900
SUBMISSION_USER=submission
VERIFIER_PRIVATE_DIR=/logs/verifier/.private
CODEX_HOME_DIR=$VERIFIER_PRIVATE_DIR/codex-home
JUDGE_TIMEOUT_SECONDS=1200

phase_group_id=
execution_error=

mkdir -p "$RESULTS_DIR" /logs/verifier
install -d -o root -g root -m 0700 "$VERIFIER_PRIVATE_DIR" "$CODEX_HOME_DIR"
chown root:"$SUBMISSION_USER" "$RESULTS_DIR"
chmod 0770 "$RESULTS_DIR"

# The candidate is deliberately run as an unprivileged user. It may read its
# own artifact directory and the public corpus mount, but not verifier code,
# hidden files, reward files, or the agent trajectory.
if [[ -d /app && ! -L /app ]]; then
    chown -R root:"$SUBMISSION_USER" /app
    find /app -type d -exec chmod 0550 {} +
    find /app -type f -perm /111 -exec chmod 0550 {} +
    find /app -type f ! -perm /111 -exec chmod 0440 {} +
else
    execution_error="missing or invalid /app directory"
fi
if [[ -d /tests && ! -L /tests ]]; then
    chown -R root:root /tests
    chmod 0700 /tests
    find /tests/data -type f -exec chmod 0600 {} +
fi
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi
rm -rf "$INDEX_DIR" "$BASELINE_INDEX_DIR"
rm -f "$OUTPUT_PATH" "$BUILD_METRICS" "$RUN_METRICS" \
    "$BASELINE_OUTPUT_PATH" "$BASELINE_BUILD_METRICS" "$BASELINE_RUN_METRICS" \
    "$REPORT_PATH" "$REWARD_PATH"

stop_group() {
    local group_id=$1
    [[ -n "$group_id" ]] || return 0
    kill -TERM -- "-$group_id" 2>/dev/null || true
    sleep 0.5
    kill -KILL -- "-$group_id" 2>/dev/null || true
}

cleanup() {
    stop_group "$phase_group_id"
    pkill -TERM -u "$SUBMISSION_USER" 2>/dev/null || true
    sleep 0.5
    pkill -KILL -u "$SUBMISSION_USER" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' INT TERM

run_phase() {
    local timeout_seconds=$1
    local stdout_path=$2
    local stderr_path=$3
    shift 3

    setsid "$@" >"$stdout_path" 2>"$stderr_path" &
    phase_group_id=$!
    local deadline=$((SECONDS + timeout_seconds))
    while kill -0 "$phase_group_id" 2>/dev/null; do
        if (( SECONDS >= deadline )); then
            stop_group "$phase_group_id"
            wait "$phase_group_id" 2>/dev/null || true
            phase_group_id=
            return 124
        fi
        sleep 1
    done
    wait "$phase_group_id"
    local status=$?
    stop_group "$phase_group_id"
    phase_group_id=
    return "$status"
}

if [[ ! -x /app/build.sh || ! -x /app/run.sh ]]; then
    execution_error="missing executable /app/build.sh or /app/run.sh"
elif [[ ! -x "$BASELINE_ROOT/build.sh" || ! -x "$BASELINE_ROOT/run.sh" ]]; then
    execution_error="missing verifier-owned corrected starter"
else
    run_phase "$BUILD_TIMEOUT_SECONDS" "$RESULTS_DIR/build.stdout.log" "$RESULTS_DIR/build.stderr.log" python3 /tests/run_with_metrics.py --metrics "$BUILD_METRICS" -- /usr/sbin/runuser -u "$SUBMISSION_USER" -- /app/build.sh --corpus /task/data/corpus.jsonl --index-dir "$INDEX_DIR"
    build_status=$?
    if (( build_status == 124 )); then
        execution_error="build.sh exceeded its timeout"
    elif (( build_status != 0 )); then
        execution_error="build.sh exited with status $build_status"
    elif [[ -z "$(find "$INDEX_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
        execution_error="build.sh produced an empty index"
    else
        run_phase "$RUN_TIMEOUT_SECONDS" "$RESULTS_DIR/run.stdout.log" "$RESULTS_DIR/run.stderr.log" python3 /tests/run_with_metrics.py --metrics "$RUN_METRICS" -- /usr/sbin/runuser -u "$SUBMISSION_USER" -- /app/run.sh --index-dir "$INDEX_DIR" --queries /tests/data/hidden_queries.jsonl --output "$OUTPUT_PATH"
        run_status=$?
        if (( run_status == 124 )); then
            execution_error="run.sh exceeded its timeout"
        elif (( run_status != 0 )); then
            execution_error="run.sh exited with status $run_status"
        elif [[ ! -s "$OUTPUT_PATH" ]]; then
            execution_error="run.sh did not produce results"
        else
            run_phase "$BASELINE_BUILD_TIMEOUT_SECONDS" "$RESULTS_DIR/starter-build.stdout.log" "$RESULTS_DIR/starter-build.stderr.log" python3 /tests/run_with_metrics.py --metrics "$BASELINE_BUILD_METRICS" -- /usr/sbin/runuser -u "$SUBMISSION_USER" -- "$BASELINE_ROOT/build.sh" --corpus /task/data/corpus.jsonl --index-dir "$BASELINE_INDEX_DIR"
            baseline_build_status=$?
            if (( baseline_build_status == 124 )); then
                execution_error="corrected starter build exceeded its timeout"
            elif (( baseline_build_status != 0 )); then
                execution_error="corrected starter build exited with status $baseline_build_status"
            elif [[ -z "$(find "$BASELINE_INDEX_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
                execution_error="corrected starter build produced an empty index"
            else
                run_phase "$BASELINE_RUN_TIMEOUT_SECONDS" "$RESULTS_DIR/starter-run.stdout.log" "$RESULTS_DIR/starter-run.stderr.log" python3 /tests/run_with_metrics.py --metrics "$BASELINE_RUN_METRICS" -- /usr/sbin/runuser -u "$SUBMISSION_USER" -- "$BASELINE_ROOT/run.sh" --index-dir "$BASELINE_INDEX_DIR" --queries /tests/data/hidden_queries.jsonl --output "$BASELINE_OUTPUT_PATH"
                baseline_run_status=$?
                if (( baseline_run_status == 124 )); then
                    execution_error="corrected starter run exceeded its timeout"
                elif (( baseline_run_status != 0 )); then
                    execution_error="corrected starter run exited with status $baseline_run_status"
                elif [[ ! -s "$BASELINE_OUTPUT_PATH" ]]; then
                    execution_error="corrected starter did not produce results"
                fi
            fi
        fi
    fi
fi

if [[ -n "$execution_error" ]]; then
    python3 - "$execution_error" "$REPORT_PATH" "$REWARD_PATH" <<'PY'
import json
import sys
from pathlib import Path

error, report_path, reward_path = sys.argv[1:]
report = {
    "status": "invalid",
    "reward_metric": "quality_gated_linear_starter_latency",
    "reward": 0.0,
    "error": error,
}
Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
Path(reward_path).write_text("0\n", encoding="utf-8")
print(json.dumps(report, indent=2))
PY
    exit 1
fi

if ! python3 /tests/grader.py --results "$OUTPUT_PATH" --baseline-results "$BASELINE_OUTPUT_PATH" --qrels /tests/data/qrels.tsv --queries /tests/data/hidden_queries.jsonl --corpus-ids /tests/data/corpus_ids.txt --reference /tests/data/reference_top100.jsonl --reference-metadata /tests/data/reference_metadata.json --categories /tests/data/categories.json --index-dir "$INDEX_DIR" --build-metrics "$BUILD_METRICS" --run-metrics "$RUN_METRICS" --baseline-run-metrics "$BASELINE_RUN_METRICS" --report "$REPORT_PATH"; then
    printf '0\n' >"$REWARD_PATH"
    exit 1
fi

python3 - "$REPORT_PATH" "$REWARD_PATH" <<'PY'
import json
import sys
from pathlib import Path

report_path, reward_path = sys.argv[1:]
report = json.loads(Path(report_path).read_text(encoding="utf-8"))
Path(reward_path).write_text(f"{float(report['reward'])}\n", encoding="utf-8")
print(json.dumps(report, indent=2, sort_keys=True))
PY

# The trajectory judge is verifier-side and runs only after all submission
# processes have been stopped. It is a compliance gate, not a retrieval
# signal, and its credentials are never exposed to the candidate.
stop_submission_processes() {
    pkill -TERM -u "$SUBMISSION_USER" 2>/dev/null || true
    sleep 0.5
    pkill -KILL -u "$SUBMISSION_USER" 2>/dev/null || true
}

stop_submission_processes
judge_status=0
judge_stdout="$RESULTS_DIR/jailbreak-judge.stdout.log"
judge_stderr="$RESULTS_DIR/jailbreak-judge.stderr.log"
install_log="$RESULTS_DIR/rewardkit-install.log"
export CODEX_HOME="$CODEX_HOME_DIR"

if [[ ! -x /opt/conda/bin/rewardkit ]]; then
    /opt/conda/bin/python -m pip install --no-cache-dir \
        "harbor-rewardkit==0.1.7" >"$install_log" 2>&1 || judge_status=$?
fi

if (( judge_status == 0 )) && [[ -x /opt/conda/bin/rewardkit ]]; then
    if [[ -z "${OPENAI_BASE_URL:-}" || -z "${OPENAI_API_KEY:-}" ]]; then
        echo "OPENAI_BASE_URL and OPENAI_API_KEY are required for the trajectory judge" \
            >"$judge_stderr"
        judge_status=78
    elif ! command -v codex >/dev/null 2>&1; then
        echo "Codex CLI is missing from the verifier image" >"$judge_stderr"
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
    /usr/bin/timeout --signal=TERM --kill-after=30s "$JUDGE_TIMEOUT_SECONDS"s \
        /opt/conda/bin/rewardkit \
        /tests \
        --workspace /app \
        --output /logs/verifier/reward.json \
        --max-concurrent-agent 1 \
        >"$judge_stdout" 2>"$judge_stderr"
    judge_status=$?
fi

SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /usr/bin/timeout --signal=TERM --kill-after=30s 60s \
    /opt/conda/bin/python /tests/finalize_reward.py \
    >"$RESULTS_DIR/finalizer.stdout.log" \
    2>"$RESULTS_DIR/finalizer.stderr.log"
finalizer_status=$?

if (( finalizer_status != 0 )); then
    exit 1
fi
if (( judge_status != 0 )); then
    exit 1
fi
