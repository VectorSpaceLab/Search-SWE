#!/usr/bin/env bash
set -euo pipefail
arguments=("$@")
index_dir=""
while (($#)); do
    if [[ "$1" == --index-dir ]]; then index_dir="$2"; fi
    shift 2
done
[[ -n "$index_dir" ]]
exec "$index_dir/native-client" "${arguments[@]}"
