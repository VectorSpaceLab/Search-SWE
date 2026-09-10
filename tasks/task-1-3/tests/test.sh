#!/usr/bin/env bash
set -u

WORK_DIR=/tmp/task-1-3-eval
INPUT_DIR=$WORK_DIR/input
INDEX_DIR=$WORK_DIR/index
SUBMISSION_OUTPUT_DIR=$WORK_DIR/output
STAGED_QUERIES=$INPUT_DIR/queries.jsonl
SUBMISSION_OUTPUT=$SUBMISSION_OUTPUT_DIR/results.jsonl
RESULTS_DIR=/logs/verifier/task-1-3-eval
OUTPUT_PATH=$RESULTS_DIR/results.jsonl
BUILD_TIMEOUT_SECONDS=3600
RUN_TIMEOUT_SECONDS=4800
MAX_OUTPUT_BYTES=$((64 * 1024 * 1024))
SUBMISSION_USER=submission
VERIFIER_PRIVATE_DIR=/logs/verifier/.private
CODEX_HOME_DIR=$VERIFIER_PRIVATE_DIR/codex-home

# Only task-allowed retrieval credentials are passed to untrusted submission
# processes. Answer-judge and Codex-Judge credentials remain verifier-only.
SUBMISSION_COMMAND=(
    /usr/sbin/runuser
    -u "$SUBMISSION_USER"
    --
    /usr/bin/setpriv
    --no-new-privs
    /usr/bin/env
    -i
    "HOME=/home/submission"
    "USER=submission"
    "LOGNAME=submission"
    "PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin"
    "LANG=C.UTF-8"
    "PYTHONUNBUFFERED=1"
    "OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}"
    "JINA_API_KEY=${JINA_API_KEY:-}"
    "HTTP_PROXY=${HTTP_PROXY:-}"
    "HTTPS_PROXY=${HTTPS_PROXY:-}"
    "NO_PROXY=${NO_PROXY:-}"
    "http_proxy=${http_proxy:-}"
    "https_proxy=${https_proxy:-}"
    "no_proxy=${no_proxy:-}"
)

build_group_id=
run_group_id=
phase_group_id=
execution_error=

mkdir -p /logs
install -d -o root -g root -m 0700 /logs/verifier
install -d -o root -g root -m 0700 "$RESULTS_DIR"
install -d -o root -g root -m 0700 "$VERIFIER_PRIVATE_DIR" "$CODEX_HOME_DIR"

if [[ -d "$WORK_DIR" && ! -L "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
elif [[ -e "$WORK_DIR" || -L "$WORK_DIR" ]]; then
    rm -f "$WORK_DIR"
fi
install -d -o root -g root -m 0711 "$WORK_DIR"
install -d -o root -g submission -m 0750 "$INPUT_DIR"
install -d -o submission -g submission -m 0750 \
    "$INDEX_DIR" "$SUBMISSION_OUTPUT_DIR"

if [[ -d /task && ! -L /task ]]; then
    chown root:root /task
    chmod 0755 /task
fi
if [[ -d /task/data && ! -L /task/data ]]; then
    chown root:root /task/data
    chmod 0755 /task/data
fi

if [[ -d /app && ! -L /app ]]; then
    chown -R submission:submission /app
    chmod 0750 /app
else
    execution_error="missing or invalid /app directory"
fi

# Corpus and documentation are read-only host mounts. Public validation is
# not mounted in this environment; do not change host file permissions.
if [[ ! -d /task/data/corpus || -L /task/data/corpus ]] \
    || ! "${SUBMISSION_COMMAND[@]}" /usr/bin/test -r /task/data/corpus; then
    execution_error="missing, invalid, or unreadable /task/data/corpus directory"
fi
if [[ ! -d /task/docs || -L /task/docs ]] \
    || ! "${SUBMISSION_COMMAND[@]}" /usr/bin/test -r /task/docs/environment.md \
    || ! "${SUBMISSION_COMMAND[@]}" /usr/bin/test -r /task/docs/available_resources.md; then
    execution_error="missing or unreadable task documentation"
fi

# The trajectory is an input to the root-side AgentJudge and is private from
# submission code.
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi

rm -f "$OUTPUT_PATH" \
    /logs/verifier/reward.json \
    /logs/verifier/reward.txt \
    /logs/verifier/reward-details.json

# Keep a valid zero reward if execution is interrupted before finalization.
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward": 0.0}\n' > /logs/verifier/reward.json

stop_group() {
    local group_id=$1
    [[ -n "$group_id" ]] || return 0
    kill -TERM -- "-$group_id" 2>/dev/null || true
    sleep 0.5
    kill -KILL -- "-$group_id" 2>/dev/null || true
}

stop_submission_processes() {
    pkill -TERM -u "$SUBMISSION_USER" 2>/dev/null || true
    sleep 1
    pkill -KILL -u "$SUBMISSION_USER" 2>/dev/null || true
}

cleanup() {
    stop_group "$run_group_id"
    stop_group "$build_group_id"
    stop_submission_processes
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
            return 124
        fi
        sleep 1
    done
    wait "$phase_group_id"
}

check_submission_before_build() {
    "${SUBMISSION_COMMAND[@]}" /bin/sh -c \
        'test -z "${ANSWER_JUDGE_API_KEY+x}" \
         && test -z "${TRAJECTORY_JUDGE_API_KEY+x}" \
         && test -z "${SILICONFLOW_API_KEY+x}" \
         && test -z "${JUDGE_API_KEY+x}" \
         && test -z "${JUDGE_MODEL_API+x}" \
         && test -z "${JUDGE_MODEL_NAME+x}" \
         && test -z "${ANSWER_JUDGE_MODEL+x}" \
         && test -z "${OPENAI_API_KEY+x}" \
         && test -z "${OPENAI_BASE_URL+x}" \
         && test -z "${TASK_1_4_JUDGE_API_KEY+x}" \
         && test -z "${CODEX_HOME+x}"' \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test -r /task/data/corpus \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test ! -r /tests/data/queries.jsonl \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test ! -r /tests/data/golden_answers.jsonl \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test ! -w /logs/verifier
}

check_submission_after_staging() {
    "${SUBMISSION_COMMAND[@]}" /usr/bin/test -r "$STAGED_QUERIES" \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test ! -w "$STAGED_QUERIES" \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test ! -r /tests/data/golden_answers.jsonl \
        && "${SUBMISSION_COMMAND[@]}" /usr/bin/test -w "$SUBMISSION_OUTPUT_DIR"
}

if [[ -z "$execution_error" ]] && \
   [[ ! -x /app/build.sh || ! -x /app/run.sh ]]; then
    execution_error="missing executable /app/build.sh or /app/run.sh"
elif [[ -z "$execution_error" ]] && ! check_submission_before_build; then
    execution_error="submission permission or credential boundary is not configured correctly"
elif [[ -z "$execution_error" ]]; then
    run_phase "$BUILD_TIMEOUT_SECONDS" \
        "$RESULTS_DIR/build.stdout.log" \
        "$RESULTS_DIR/build.stderr.log" \
        "${SUBMISSION_COMMAND[@]}" \
        /app/build.sh \
        --corpus /task/data/corpus \
        --index-dir "$INDEX_DIR"
    build_status=$?
    build_group_id=$phase_group_id
    if (( build_status == 124 )); then
        execution_error="build.sh exceeded its timeout"
    elif (( build_status != 0 )); then
        execution_error="build.sh exited with status $build_status"
    elif ! install \
        -o root \
        -g submission \
        -m 0440 \
        /tests/data/queries.jsonl \
        "$STAGED_QUERIES"; then
        execution_error="failed to stage hidden queries"
    elif ! check_submission_after_staging; then
        execution_error="submission query staging boundary is not configured correctly"
    else
        run_phase "$RUN_TIMEOUT_SECONDS" \
            "$RESULTS_DIR/run.stdout.log" \
            "$RESULTS_DIR/run.stderr.log" \
            /opt/conda/bin/python /tests/run_queries.py \
            --queries "$STAGED_QUERIES" \
            --index-dir "$INDEX_DIR" \
            --output "$SUBMISSION_OUTPUT" \
            --logs-dir "$RESULTS_DIR/query_logs" \
            --timeout 900 \
            --concurrency 5
        run_status=$?
        run_group_id=$phase_group_id
        stop_submission_processes
        if (( run_status == 124 )); then
            execution_error="query execution exceeded its shared safety timeout"
        elif (( run_status != 0 )); then
            execution_error="run.sh exited with status $run_status"
        elif [[ ! -f "$SUBMISSION_OUTPUT" || -L "$SUBMISSION_OUTPUT" ]]; then
            execution_error="run.sh did not produce a regular output file"
        else
            output_size=$(stat -c %s -- "$SUBMISSION_OUTPUT" 2>/dev/null || printf '%s' -1)
            if (( output_size < 0 || output_size > MAX_OUTPUT_BYTES )); then
                execution_error="submission output size is invalid"
            elif ! install \
                -o root \
                -g root \
                -m 0600 \
                "$SUBMISSION_OUTPUT" \
                "$OUTPUT_PATH"; then
                execution_error="failed to collect submission output"
            fi
        fi
    fi
fi

stop_submission_processes

SEARCH_SWE_EXECUTION_ERROR="$execution_error" \
    /usr/bin/env -u OPENAI_API_KEY -u OPENAI_BASE_URL \
    /usr/bin/timeout --signal=TERM --kill-after=30s 1800s /opt/conda/bin/python /tests/grader.py
grader_status=$?

# Root-side second Codex AgentJudge. Its credentials are intentionally not in
# SUBMISSION_COMMAND.
judge_stdout="$RESULTS_DIR/jailbreak-judge.stdout.log"
judge_stderr="$RESULTS_DIR/jailbreak-judge.stderr.log"
install_log="$RESULTS_DIR/rewardkit-install.log"
judge_status=0
export CODEX_HOME="$CODEX_HOME_DIR"

judge_task_dir=$VERIFIER_PRIVATE_DIR/judge-task
if ! /opt/conda/bin/python /tests/configure_trajectory_judge.py \
    --template /tests/jailbreak_judge/codex.toml \
    --output "$judge_task_dir" --home "$CODEX_HOME_DIR" \
    >"$judge_stdout" 2>"$judge_stderr"; then
    judge_status=78
fi

if (( judge_status == 0 )) && [[ ! -x /opt/conda/bin/rewardkit ]]; then
    /opt/conda/bin/python -m pip install --no-cache-dir \
        "harbor-rewardkit==0.1.7" >"$install_log" 2>&1 || judge_status=$?
fi

if (( judge_status == 0 )) && [[ -x /opt/conda/bin/rewardkit ]]; then
    /usr/bin/env -u ANSWER_JUDGE_API_KEY -u ANSWER_JUDGE_BASE_URL -u ANSWER_JUDGE_MODEL_NAME \
    /usr/bin/timeout --signal=TERM --kill-after=30s 3600s /opt/conda/bin/rewardkit \
        "$judge_task_dir" \
        --workspace /app \
        --output /logs/verifier/reward.json \
        --max-concurrent-agent 1 \
        >"$judge_stdout" 2>"$judge_stderr" || judge_status=$?
else
    echo "Trajectory judge configuration, installation, or binary check failed" >>"$judge_stderr"
    if (( judge_status == 0 )); then
        judge_status=127
    fi
fi

SEARCH_SWE_JUDGE_STATUS="$judge_status" \
    /opt/conda/bin/python /tests/finalize_reward.py
finalizer_status=$?

if (( finalizer_status != 0 )); then
    exit "$finalizer_status"
fi
if (( grader_status != 0 || judge_status != 0 )); then
    exit 1
fi
exit 0
