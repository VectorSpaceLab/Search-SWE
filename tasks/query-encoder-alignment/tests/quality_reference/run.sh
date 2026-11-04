#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /opt/conda/bin/python "$SCRIPT_DIR/baseline.py" --projection "$SCRIPT_DIR/ridge.npz" "$@"
