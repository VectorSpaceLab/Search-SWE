#!/usr/bin/env bash
# Task-specific evaluation invoked by the timeout supervisor.
set -u
set -o pipefail

LOG_DIR=/logs/verifier/task-2-3-eval
WORK_DIR=/tmp/task-2-3-verifier
CANDIDATE_RUNTIME=$WORK_DIR/candidate-runtime
CANDIDATE_OUTPUT=$WORK_DIR/candidate-output
CANDIDATE_HOME=$WORK_DIR/candidate-home
CANDIDATE_TMP=$WORK_DIR/candidate-tmp
CANDIDATE_QUERIES=$WORK_DIR/candidate-queries.jsonl
STARTER_OUTPUT=$WORK_DIR/starter-results.jsonl
STARTER_REPORT=$WORK_DIR/starter-report.json
STARTER_TIME=$WORK_DIR/starter-time.txt
CANDIDATE_RESULTS=$CANDIDATE_OUTPUT/results.jsonl
CANDIDATE_REPEAT_RESULTS=$CANDIDATE_OUTPUT/results-repeat.jsonl
CANDIDATE_TIME=$WORK_DIR/candidate-time.txt
SUBMISSION_DIR=/app/submission
HIDDEN_QUERIES=/tests/data/queries.jsonl
RUN_TIMEOUT_SECONDS=1800

phase_group_id=

mkdir -p /logs/verifier
rm -rf "$LOG_DIR" "$WORK_DIR"
mkdir -p "$LOG_DIR" "$CANDIDATE_RUNTIME" "$CANDIDATE_OUTPUT" \
    "$CANDIDATE_HOME" "$CANDIDATE_TMP"

stop_group() {
    local group_id=$1
    [[ -n "$group_id" ]] || return 0
    kill -TERM -- "-$group_id" 2>/dev/null || true
    sleep 0.5
    kill -KILL -- "-$group_id" 2>/dev/null || true
}

cleanup() {
    stop_group "$phase_group_id"
    pkill -KILL -u submission 2>/dev/null || true
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
    phase_group_id=
    return "$status"
}

run_timed_phase() {
    local duration_path=$1
    shift
    local started_ns finished_ns status
    started_ns=$(date +%s%N)
    run_phase "$@"
    status=$?
    finished_ns=$(date +%s%N)
    /opt/conda/bin/python - "$started_ns" "$finished_ns" "$duration_path" <<'PY'
from pathlib import Path
import sys

elapsed = (int(sys.argv[2]) - int(sys.argv[1])) / 1_000_000_000
Path(sys.argv[3]).write_text(f"{elapsed:.9f}\n", encoding="utf-8")
PY
    return "$status"
}

assert_no_submission_processes() {
    local pids
    pids=$(pgrep -u submission 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "submission-owned processes remain: $pids" >&2
        pkill -TERM -u submission 2>/dev/null || true
        sleep 0.5
        pkill -KILL -u submission 2>/dev/null || true
        return 1
    fi
}

execution_error=
if [[ ! -d "$SUBMISSION_DIR" || -L "$SUBMISSION_DIR" ]]; then
    execution_error="/app/submission must be a regular directory"
elif [[ ! -f "$SUBMISSION_DIR/run.sh" || -L "$SUBMISSION_DIR/run.sh" || ! -x "$SUBMISSION_DIR/run.sh" ]]; then
    execution_error="missing executable /app/submission/run.sh"
elif [[ -n "$(find "$SUBMISSION_DIR" -type l -print -quit 2>/dev/null)" ]]; then
    execution_error="submission must not contain symbolic links"
else
    cp -a "$SUBMISSION_DIR/." "$CANDIDATE_RUNTIME/"
fi

chmod 700 /tests /tests/data
chmod 600 /tests/data/queries.jsonl /tests/data/ground_truth.jsonl
# Fixed /task inputs are read-only host mounts; never change their ownership.
chown -R root:root /tests "$CANDIDATE_RUNTIME"
chmod -R u=rwX,go=rX "$CANDIDATE_RUNTIME"
chown -R submission:submission "$CANDIDATE_OUTPUT" "$CANDIDATE_HOME" "$CANDIDATE_TMP"
chmod 700 "$CANDIDATE_OUTPUT" "$CANDIDATE_HOME" "$CANDIDATE_TMP"
cp "$HIDDEN_QUERIES" "$CANDIDATE_QUERIES"
chown submission:submission "$CANDIDATE_QUERIES"
chmod 400 "$CANDIDATE_QUERIES"
if [[ -d /logs/agent ]]; then
    chown -R root:root /logs/agent
    chmod 700 /logs/agent
fi

run_candidate() {
    local output_path=$1
    local stdout_path=$2
    local stderr_path=$3
    run_phase "$RUN_TIMEOUT_SECONDS" "$stdout_path" "$stderr_path" \
        /usr/sbin/runuser -u submission -- \
            /usr/bin/env -i \
            HOME="$CANDIDATE_HOME" \
            TMPDIR="$CANDIDATE_TMP" \
            PATH=/opt/conda/bin:/usr/bin:/bin \
            LD_LIBRARY_PATH=/opt/conda/lib \
            LANG=C.UTF-8 \
            LC_ALL=C.UTF-8 \
            HF_HUB_OFFLINE=1 \
            TRANSFORMERS_OFFLINE=1 \
            PYTHONDONTWRITEBYTECODE=1 \
            PYTHONUNBUFFERED=1 \
            "$CANDIDATE_RUNTIME/run.sh" \
                --doc-vectors /task/data/doc.npy \
                --queries "$CANDIDATE_QUERIES" \
                --output "$output_path" \
                --top-k 1
}

if [[ -z "$execution_error" ]]; then
    run_timed_phase "$STARTER_TIME" \
        "$RUN_TIMEOUT_SECONDS" \
        "$LOG_DIR/starter.stdout.log" \
        "$LOG_DIR/starter.stderr.log" \
        /tests/starter/run.sh \
            --doc-vectors /task/data/doc.npy \
            --queries "$HIDDEN_QUERIES" \
            --output "$STARTER_OUTPUT" \
            --report "$STARTER_REPORT" \
            --top-k 1
    starter_status=$?
    if (( starter_status == 124 )); then
        execution_error="starter baseline exceeded its timeout"
    elif (( starter_status != 0 )); then
        execution_error="starter baseline exited with status $starter_status"
    fi
fi

if [[ -z "$execution_error" ]]; then
    started_ns=$(date +%s%N)
    run_candidate "$CANDIDATE_RESULTS" \
        "$LOG_DIR/candidate.stdout.log" \
        "$LOG_DIR/candidate.stderr.log"
    candidate_status=$?
    finished_ns=$(date +%s%N)
    /opt/conda/bin/python - "$started_ns" "$finished_ns" "$CANDIDATE_TIME" <<'PY'
from pathlib import Path
import sys

elapsed = (int(sys.argv[2]) - int(sys.argv[1])) / 1_000_000_000
Path(sys.argv[3]).write_text(f"{elapsed:.9f}\n", encoding="utf-8")
PY
    if (( candidate_status == 124 )); then
        execution_error="candidate run exceeded its timeout"
    elif (( candidate_status != 0 )); then
        execution_error="candidate run exited with status $candidate_status"
    elif ! assert_no_submission_processes; then
        execution_error="candidate run left background processes"
    elif [[ ! -f "$CANDIDATE_RESULTS" || -L "$CANDIDATE_RESULTS" ]]; then
        execution_error="candidate did not produce a regular results file"
    fi
fi

if [[ -z "$execution_error" ]]; then
    run_candidate "$CANDIDATE_REPEAT_RESULTS" \
        "$LOG_DIR/candidate-repeat.stdout.log" \
        "$LOG_DIR/candidate-repeat.stderr.log"
    repeat_status=$?
    if (( repeat_status != 0 )); then
        execution_error="candidate repeat run exited with status $repeat_status"
    elif ! assert_no_submission_processes; then
        execution_error="candidate repeat run left background processes"
    elif ! cmp -s "$CANDIDATE_RESULTS" "$CANDIDATE_REPEAT_RESULTS"; then
        execution_error="candidate output is not deterministic"
    fi
fi

grader_status=0
SEARCH_SWE_STARTER_OUTPUT="$STARTER_OUTPUT" \
SEARCH_SWE_CANDIDATE_OUTPUT="$CANDIDATE_RESULTS" \
SEARCH_SWE_STARTER_REPORT="$STARTER_REPORT" \
SEARCH_SWE_STARTER_TIME_FILE="$STARTER_TIME" \
SEARCH_SWE_CANDIDATE_TIME_FILE="$CANDIDATE_TIME" \
SEARCH_SWE_EXECUTION_ERROR="$execution_error" \
    /opt/conda/bin/python /tests/grader.py \
        >"$LOG_DIR/grader.stdout.log" 2>"$LOG_DIR/grader.stderr.log" \
        || grader_status=$?
exit "$grader_status"
