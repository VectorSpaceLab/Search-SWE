#!/usr/bin/env bash
set -u

TASK_ID=task-2-1
RESULTS_DIR=/logs/verifier/${TASK_ID}-eval
SUBMISSION_USER=submission
VERIFIER_PRIVATE_DIR=/logs/verifier/.private
execution_error=

mkdir -p /logs
install -d -o root -g root -m 0700 /logs/verifier
install -d -o root -g root -m 0700 "$RESULTS_DIR"
install -d -o root -g root -m 0700 "$VERIFIER_PRIVATE_DIR"

# Keep the submitted artifact readable and executable by the unprivileged
# verifier user, while preventing it from modifying the artifact or verifier
# state during evaluation.
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

# Fixed inputs are read-only host mounts; do not chmod/chown their contents.
for corpus_file in /task/data/corpus.jsonl; do
    if [[ ! -f "$corpus_file" || -L "$corpus_file" ]] \
        || ! /usr/sbin/runuser -u submission -- test -r "$corpus_file"; then
        execution_error="missing, invalid, or unreadable corpus file: $corpus_file"
    fi
done

if [[ ! -d /task/models/bge-reranker-large || -L /task/models/bge-reranker-large ]] \
    || ! /usr/sbin/runuser -u submission -- test -r /task/models/bge-reranker-large/model.safetensors; then
    execution_error="missing, invalid, or unreadable fixed reranker model"
fi

# Public validation is not mounted in the verifier. Hidden inputs remain
# root-owned; grader.py copies only queries into the submission work directory.
if [[ -d /tests && ! -L /tests ]]; then
    chown root:root /tests
    chmod 0700 /tests
fi
if [[ -d /tests/data && ! -L /tests/data ]]; then
    chown -R root:root /tests/data
    chmod 0700 /tests/data
    find /tests/data -type f -exec chmod 0600 {} +
fi

# The root-side AgentJudge consumes the trajectory. Submission code must not
# be able to read, replace, or truncate it during build/run.
if [[ -d /logs/agent && ! -L /logs/agent ]]; then
    chown root:root /logs/agent
    chmod 0700 /logs/agent
    if [[ -f /logs/agent/trajectory.json && ! -L /logs/agent/trajectory.json ]]; then
        chown root:root /logs/agent/trajectory.json
        chmod 0600 /logs/agent/trajectory.json
    fi
fi

rm -f /logs/verifier/reward.json \
    /logs/verifier/reward.txt \
    /logs/verifier/reward-details.json \
    /logs/verifier/report.json

stop_submission_processes() {
    pkill -TERM -u "$SUBMISSION_USER" 2>/dev/null || true
    sleep 1
    pkill -KILL -u "$SUBMISSION_USER" 2>/dev/null || true
}

cleanup() {
    stop_submission_processes
}

trap cleanup EXIT
trap 'exit 143' INT TERM

stop_submission_processes
SEARCH_SWE_EXECUTION_ERROR="$execution_error" \
    /opt/conda/bin/python /tests/grader.py
grader_status=$?

# Run the verifier-side second Codex only after all submission-owned processes
# have been terminated. Judge credentials were never passed to build.sh or run.sh.
stop_submission_processes
judge_stdout="$RESULTS_DIR/jailbreak-judge.stdout.log"
judge_stderr="$RESULTS_DIR/jailbreak-judge.stderr.log"
judge_status=0

if [[ -z "${OPENAI_BASE_URL:-}" || -z "${OPENAI_API_KEY:-}" ]]; then
    printf '%s\n' \
        'OPENAI_BASE_URL and OPENAI_API_KEY are required for the OpenRouter DeepSeek judge' \
        > "$judge_stderr"
    judge_status=78
fi

if (( judge_status == 0 )); then
    /opt/conda/bin/python /tests/rewardkit_deepseek.py \
        /tests \
        --workspace /app \
        --output /logs/verifier/reward.json \
        --max-concurrent-agent 1 \
        --judge deepseek-codex \
        --model deepseek/deepseek-v4.1-flash \
        >"$judge_stdout" 2>"$judge_stderr" || judge_status=$?
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
