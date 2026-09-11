#!/usr/bin/env bash
set -euo pipefail

index_dir=''
queries=''
output=''

while [[ $# -gt 0 ]]; do
    case "$1" in
        --index-dir)
            index_dir=$2
            shift 2
            ;;
        --queries)
            queries=$2
            shift 2
            ;;
        --output)
            output=$2
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

[[ -n "$index_dir" && -n "$queries" && -n "$output" ]] || {
    echo "usage: run.sh --index-dir PATH --queries PATH --output PATH" >&2
    exit 2
}

exec python3 "$(dirname "$0")/src/sparse_retrieval.py" search \
    --index-dir "$index_dir" \
    --queries "$queries" \
    --output "$output"
