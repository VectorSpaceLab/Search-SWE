"""Write the public layer-streamed fixed-probe starter with native JSON transport."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

PREPARE = r'''#!/usr/bin/env bash
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
'''

RUN = r'''#!/usr/bin/env bash
set -euo pipefail
arguments=("$@")
index_dir=""
while (($#)); do
    if [[ "$1" == --index-dir ]]; then index_dir="$2"; fi
    shift 2
done
[[ -n "$index_dir" ]]
exec "$index_dir/native-client" "${arguments[@]}"
'''

BASE_CONFIGURATION = {'model': 'Qwen/Qwen2.5-7B',
 'revision': 'd149729398750b98c0af14eb82c78cfe92750796',
 'probe': 'Read-only /task/models/base; all 28 serialized NF4 double-quantized decoder layers, '
          'complete BF16 input embeddings, original tokenizer, and supplied 64,439-row BF16 '
          'diagnostic output head remain fixed.',
 'inference': 'Reconstruct exact NF4 Params4bit state from supplied safetensors, keep packed layer '
              'weights on CPU, move only the current decoder layer to CUDA for its forward, and '
              'restore its fixed CPU parameters immediately afterward. BF16 compute, SDPA '
              'attention, no optimizer updates.',
 'query_alignment': 'Use supplied input_ids without re-tokenization or truncation; compute every '
                    'marked target position at causal index j-1. For multi-position spans, select '
                    'the strongest selected-head alternative-to-actual-token contrast, matching '
                    'the public starter.',
 'candidate_pool': 'Boundary-aware case-insensitive target_text occurrences in training outputs '
                   'with source-token surfaces from supplied base-token-alternatives.npz and '
                   'target NLLs from supplied base-token-nll.npz.',
 'ranking': 'First apply the public starter training-IDF lexical source gate (top-three '
            'aggregation, minimum one rare matching term, ten candidate rows, aggregate at least '
            '1.0 and 1.12 margin). Otherwise rank by fresh fixed-probe source-token mass, then '
            'training-only maximum target-token NLL, then opaque ID.',
 'request_state': 'No query hidden states, logits, features, scores or rankings persist between '
                  'requests. Cached output rows, candidate pools and text statistics depend only '
                  'on fixed training inputs and the supplied probe.',
 'ranker_training': False,
 'external_services': False,
 'dataset_terms': 'CC BY-NC 4.0 research/noncommercial',
 'provided_training_features': ['/task/data/base-nll/base-token-nll.npz',
                                '/task/data/base-alternatives/base-token-alternatives.npz'],
 'fixed_layers': 28,
 'probe_head_rows': 64439,
 'provided_assets_bytes': 4868975243}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Choose an empty submission directory")
    args.output.chmod(0o755)
    tools = Path(__file__).resolve().parent
    for name, content in [("prepare.sh", PREPARE), ("run.sh", RUN)]:
        path = args.output / name
        path.write_text(content)
        path.chmod(0o755)
    service = args.output / "retriever_service.py"
    service.write_bytes((tools / "streamed_source.py").read_bytes())
    service.chmod(0o644)
    config = copy.deepcopy(BASE_CONFIGURATION)
    sources = ["retrieval_index.py", "candidate_features.py", "source_coherence.py",
               "fixed_features.py", "token_contract.py", "lexical_source.py",
               "compact_probe.py", "native_client.cpp", "streamed_source.py"]
    config["public_tool_sha256"] = {
        name: hashlib.sha256((tools / name).read_bytes()).hexdigest() for name in sources
    }
    config["submission_code_sha256"] = {
        name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
        for name in ["prepare.sh", "run.sh", "retriever_service.py"]
    }
    metadata = {
        "schema_version": 1,
        "method": "Public training-text routing with all28 fixed NF4 layers streamed from CPU and native IPC",
        "configuration": config,
        "frozen_artifacts": [],
    }
    path = args.output / "submission.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n")
    path.chmod(0o644)


if __name__ == "__main__":
    main()
