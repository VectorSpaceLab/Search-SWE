#!/usr/bin/env bash
set -u

mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"gold_recall_at_5": 0.0}\n' \
    > /logs/verifier/reward.json

cleanup_submission_processes() {
    /usr/bin/pkill -TERM -u 65534 2>/dev/null || true
    /usr/bin/pkill -KILL -u 65534 2>/dev/null || true
}
trap cleanup_submission_processes EXIT
trap 'exit 143' TERM INT HUP

/opt/conda/bin/python /tests/verify.py
