#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
data_dir=""
model_dir=""
index_dir=""
while (($#)); do
    case "$1" in
        --data-dir) data_dir="$2"; shift 2 ;;
        --model-dir) model_dir="$2"; shift 2 ;;
        --index-dir) index_dir="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ -n "$data_dir" && -n "$model_dir" && -n "$index_dir" ]]
mkdir -p "$index_dir"
c++ -O2 -std=c++17 /task/tools/native_client.cpp -o "$index_dir/native-client"
exec /opt/conda/bin/python "$script_dir/retriever_service.py" prepare \
    --data-dir "$data_dir" \
    --model-dir "$model_dir" \
    --index-dir "$index_dir"
