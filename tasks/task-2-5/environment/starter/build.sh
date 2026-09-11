#!/usr/bin/env bash
set -euo pipefail

corpus=''
index_dir=''
cache_dir=''

while [[ $# -gt 0 ]]; do
    case "$1" in
        --corpus)
            corpus=$2
            shift 2
            ;;
        --index-dir)
            index_dir=$2
            shift 2
            ;;
        --cache-dir)
            cache_dir=$2
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

[[ -n "$corpus" && -n "$index_dir" ]] || {
    echo "usage: build.sh --corpus PATH --index-dir PATH [--cache-dir PATH]" >&2
    exit 2
}

args=(--corpus "$corpus" --index-dir "$index_dir")
if [[ -n "$cache_dir" ]]; then
    args+=(--cache-dir "$cache_dir")
fi

exec python3 "$(dirname "$0")/src/sparse_retrieval.py" build "${args[@]}"
