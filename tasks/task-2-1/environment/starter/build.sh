#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PATH="${SEARCH_SWE_RERANKER_MODEL:-/task/models/bge-reranker-large}"
PYTHON_BIN="${SEARCH_SWE_PYTHON:-/opt/conda/bin/python}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

corpus=""
index_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus)
      corpus="$2"
      shift 2
      ;;
    --index-dir)
      index_dir="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$corpus" || -z "$index_dir" ]]; then
  echo "Usage: build.sh --corpus PATH --index-dir PATH" >&2
  exit 1
fi

if [[ ! -r "$corpus" ]]; then
  echo "Corpus is not readable: $corpus" >&2
  exit 1
fi
if [[ ! -f "$MODEL_PATH/config.json" || ! -f "$MODEL_PATH/model.safetensors" ]]; then
  echo "Fixed reranker model is incomplete: $MODEL_PATH" >&2
  exit 1
fi

if [[ -f "$index_dir/service.pid" ]]; then
  old_pid="$(<"$index_dir/service.pid")"
  if [[ "$old_pid" =~ ^[0-9]+$ ]]; then
    kill "$old_pid" 2>/dev/null || true
  fi
fi

mkdir -p "$index_dir"
rm -f "$index_dir/service.json" "$index_dir/service.pid"
PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -m src.build_index \
  --corpus "$corpus" \
  --index-dir "$index_dir"

nohup env PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -m src.server \
  --index-dir "$index_dir" \
  --model "$MODEL_PATH" \
  >"$index_dir/service.log" 2>&1 &
printf '%s\n' "$!" > "$index_dir/service.pid"

"$PYTHON_BIN" - "$index_dir" <<'PY'
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

index_dir = Path(sys.argv[1])
service_path = index_dir / "service.json"
pid_path = index_dir / "service.pid"
deadline = time.time() + 900
while time.time() < deadline:
    try:
        if pid_path.is_file():
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                log = (index_dir / "service.log").read_text(
                    encoding="utf-8", errors="replace"
                )
                raise SystemExit(
                    "starter reranking service exited before readiness:\n" + log[-8000:]
                )
        service = json.loads(service_path.read_text(encoding="utf-8"))
        with urlopen(
            f"http://{service['host']}:{service['port']}/health", timeout=2
        ) as response:
            if response.status == 200:
                break
    except (OSError, ValueError):
        pass
    time.sleep(0.2)
else:
    log = (index_dir / "service.log").read_text(
        encoding="utf-8", errors="replace"
    )
    raise SystemExit(
        "starter reranking service did not become ready within 900 seconds:\n"
        + log[-8000:]
    )
PY
