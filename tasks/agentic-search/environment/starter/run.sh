#!/usr/bin/env bash
set -euo pipefail
exec "${PYTHON:-/opt/conda/bin/python}" "$(dirname "$0")/src/run_search.py" "$@"
