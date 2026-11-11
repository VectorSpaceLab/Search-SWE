#!/usr/bin/env bash
set -u

RESULTS_DIR=/logs/artifacts/sparse-retrieval-pruning-eval
SUBMISSION_USER=submission
JUDGE_TIMEOUT_SECONDS=1200
mkdir -p /logs/verifier
chmod 0700 /logs/verifier
printf '0\n' >/logs/verifier/reward.txt
printf '{"reward":0}\n' >/logs/verifier/reward.json
# Hide all verifier inputs from submission UID except the query file. Landlock
# exposes that one file only during search, never during the index build.
chmod 0711 /tests /tests/data
chmod 0600 /tests/data/*
chmod 0644 /tests/data/hidden_queries.jsonl
if [[ -d /logs/agent ]]; then chmod 0700 /logs/agent; fi
cleanup() {
    local status=$?
    pkill -KILL -u "$SUBMISSION_USER" 2>/dev/null || true
    # Separate verifiers export /logs/verifier, not /logs/artifacts. Copy only
    # completed diagnostics, after all timed children and the judge have exited.
    /opt/conda/bin/python /tests/collect_artifacts.py || status=1
    exit "$status"
}
trap cleanup EXIT
if ! /usr/bin/env -i PATH=/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
    JAVA_HOME=/opt/java/openjdk \
    /opt/conda/bin/python /tests/evaluate.py; then exit 1; fi

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

if [[ -z "${OPENAI_BASE_URL:-}" || -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_BASE_URL and OPENAI_API_KEY are required for the DeepSeek trajectory judge" \
        >"$judge_stderr"
    judge_status=78
fi

if (( judge_status == 0 )); then
    /usr/bin/timeout --signal=TERM --kill-after=30s "$JUDGE_TIMEOUT_SECONDS"s \
        /opt/conda/bin/python /tests/rewardkit_deepseek.py \
        /tests \
        --workspace /app \
        --output /logs/verifier/reward.json \
        --max-concurrent-agent 1 \
        --judge deepseek-codex \
        --model deepseek/deepseek-v4.1-flash \
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
