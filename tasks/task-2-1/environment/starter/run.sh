#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
PYTHON_BIN="${SEARCH_SWE_PYTHON:-/opt/conda/bin/python}"

index_dir=""
queries=""
output=""
top_k=5
while [[ $# -gt 0 ]]; do
  case "$1" in
    --index-dir)
      index_dir="$2"
      shift 2
      ;;
    --queries)
      queries="$2"
      shift 2
      ;;
    --output)
      output="$2"
      shift 2
      ;;
    --top-k)
      top_k="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$index_dir" || -z "$queries" || -z "$output" ]]; then
  echo "Usage: run.sh --index-dir PATH --queries PATH --output PATH --top-k K" >&2
  exit 1
fi
if [[ ! "$top_k" =~ ^[0-9]+$ ]] || (( top_k < 1 || top_k > 100 )); then
  echo "--top-k must be an integer between 1 and 100" >&2
  exit 1
fi

"$PYTHON_BIN" - "$index_dir" "$queries" "$output" "$top_k" <<'PY'
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

index_dir, queries_path, output_path = map(Path, sys.argv[1:4])
top_k = int(sys.argv[4])
service = json.loads((index_dir / "service.json").read_text(encoding="utf-8"))
url = f"http://{service['host']}:{service['port']}/rerank"

output_path.parent.mkdir(parents=True, exist_ok=True)
with queries_path.open(encoding="utf-8") as source, output_path.open(
    "w", encoding="utf-8"
) as target:
    for line_number, line in enumerate(source, 1):
        if not line.strip():
            continue
        query = json.loads(line)
        request = Request(
            url,
            data=json.dumps({"query": query, "top_k": top_k}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
        target.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
PY
