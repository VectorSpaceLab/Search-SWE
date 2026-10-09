#!/usr/bin/env bash
# Task-specific evaluation invoked by the timeout supervisor.
set -u
set -o pipefail

LOG_DIR=/logs/verifier/code-embedding-finetuning-eval

mkdir -p /logs/verifier "$LOG_DIR"

grader_status=0
/opt/conda/bin/python /tests/grader.py \
    >"$LOG_DIR/grader.stdout.log" 2>"$LOG_DIR/grader.stderr.log" \
    || grader_status=$?
exit "$grader_status"
