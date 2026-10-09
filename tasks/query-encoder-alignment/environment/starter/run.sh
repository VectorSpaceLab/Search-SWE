#!/usr/bin/env bash
set -euo pipefail

doc_vectors_path=
corpus_path=/task/data/corpus.jsonl
queries_path=
ground_truth_path=
output_path=
report_path=
top_k=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --doc-vectors) doc_vectors_path=${2:?missing value for --doc-vectors}; shift 2 ;;
        --corpus) corpus_path=${2:?missing value for --corpus}; shift 2 ;;
        --queries) queries_path=${2:?missing value for --queries}; shift 2 ;;
        --ground-truth) ground_truth_path=${2:?missing value for --ground-truth}; shift 2 ;;
        --output) output_path=${2:?missing value for --output}; shift 2 ;;
        --report) report_path=${2:?missing value for --report}; shift 2 ;;
        --top-k) top_k=${2:?missing value for --top-k}; shift 2 ;;
        *) echo "unexpected argument: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$doc_vectors_path" || -z "$queries_path" || -z "$output_path" ]]; then
    echo "--doc-vectors, --queries, and --output are required" >&2
    exit 2
fi

command=(
    /opt/conda/bin/python /app/starter/src/run_search.py
    --doc-vectors "$doc_vectors_path" \
    --corpus "$corpus_path" \
    --queries "$queries_path" \
    --output "$output_path" \
    --top-k "$top_k"
)
if [[ -n "$ground_truth_path" ]]; then
    command+=(--ground-truth "$ground_truth_path")
fi
if [[ -n "$report_path" ]]; then
    command+=(--report "$report_path")
fi
"${command[@]}"
