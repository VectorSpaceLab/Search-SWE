#!/usr/bin/env bash
set -euo pipefail

output_dir=/app/submission
if [[ "${1:-}" == "--output-dir" ]]; then
    output_dir=${2:?missing value for --output-dir}
    shift 2
fi
if [[ "${1:-}" != "" ]]; then
    echo "unexpected argument: $1" >&2
    exit 2
fi

rm -rf "$output_dir/model"
mkdir -p "$output_dir"
export WANDB_MODE=disabled
export TOKENIZERS_PARALLELISM=false

args=(
    --model_name_or_path /task/models/bge-base-en-v1.5
    --train_data /task/data/train.jsonl
    --output_dir "$output_dir/model"
    --train_group_size 1
    --query_max_len 512
    --passage_max_len 512
    --per_device_train_batch_size 8
    --dataloader_drop_last True
    --learning_rate 1e-5
    --num_train_epochs 1
    --warmup_steps 0.1
    --gradient_checkpointing
    --logging_steps 50
    --save_strategy no
    --fp16
    --sentence_pooling_method cls
    --normalize_embeddings True
    --temperature 0.02
    --report_to none
)

exec /opt/conda/bin/python -m FlagEmbedding.finetune.embedder.encoder_only.base "${args[@]}"
