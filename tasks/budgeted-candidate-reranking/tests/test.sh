#!/usr/bin/env bash
set -eu
install -d -o root -g root -m 0700 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
chmod 0700 /tests
exec /opt/conda/bin/python /tests/grader.py
