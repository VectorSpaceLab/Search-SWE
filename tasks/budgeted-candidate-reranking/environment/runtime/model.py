"""Fixed, code-free model loader and authoritative weighted-token accounting."""
import hashlib
import json
import math
from pathlib import Path
import time

MODEL = '/task/models/Qwen3-1.7B'
BUDGET = 2048
OUTPUT_WEIGHT = 4
GPU_LIMIT = 24 << 30


def deployment_config(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or set(config) - {'attention', 'cpu_threads'}:
        raise ValueError('deployment.json supports only attention and cpu_threads')
    config = {'attention': config.get('attention', 'sdpa'),
              'cpu_threads': config.get('cpu_threads', 8)}
    if config['attention'] not in ('sdpa', 'eager'):
        raise ValueError('attention must be sdpa or eager')
    if type(config['cpu_threads']) is not int or not 1 <= config['cpu_threads'] <= 16:
        raise ValueError('cpu_threads must be an integer in [1,16]')
    return config


class Meter:
    """Owned by the supervisor, never by the submitted process or a connection."""
    def __init__(self, budget=BUDGET):
        self.budget = budget
        self.spent = 0
        self.calls = []

    def reserve(self, input_tokens, maximum_output):
        cost = input_tokens + OUTPUT_WEIGHT * maximum_output
        if self.spent + cost > self.budget:
            raise ValueError('weighted token budget exceeded; request not executed')
        self.spent += cost
        record = {'input_tokens': input_tokens, 'reserved_output': maximum_output,
                  'output_tokens': None, 'charged_tokens': cost, 'status': 'reserved'}
        self.calls.append(record)
        return record

    def settle(self, record, actual_output):
        if record['status'] != 'reserved' or not 0 <= actual_output <= record['reserved_output']:
            raise RuntimeError('Invalid or repeated settlement')
        cost = record['input_tokens'] + OUTPUT_WEIGHT * actual_output
        self.spent -= record['charged_tokens'] - cost
        record.update(output_tokens=actual_output, charged_tokens=cost, status='complete')


def verify_model(root, manifest):
    for name, expected in json.loads(Path(manifest).read_text()).items():
        p = Path(root) / name
        if not p.is_file() or p.is_symlink():
            raise RuntimeError('Missing/linked model asset: ' + name)
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(8 << 20), b''):
                h.update(block)
        if h.hexdigest() != expected:
            raise RuntimeError('Model asset hash mismatch: ' + name)


class FixedModel:
    def __init__(self, config, model_dir=MODEL):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.torch = torch
        torch.set_num_threads(config['cpu_threads'])
        torch.manual_seed(0)
        # Leave 2 GiB of the public VRAM allowance for CUDA/context overhead.
        total = torch.cuda.get_device_properties(0).total_memory
        if total < GPU_LIMIT:
            raise RuntimeError('At least 24 GiB physical VRAM is required')
        torch.cuda.set_per_process_memory_fraction((22 << 30) / total, 0)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True,
                                                       trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False,
            use_safetensors=True, dtype=torch.bfloat16, device_map='cuda:0',
            attn_implementation=config['attention']).eval()
        self.info = {'device': torch.cuda.get_device_name(0), 'dtype': 'bfloat16',
                     'config': config, 'thinking': False, 'decode': 'greedy'}

    def prepare(self, request, candidate_ids):
        if not isinstance(request, dict) or set(request) - {
                'type', 'messages', 'max_new_tokens', 'logprob_tokens', 'candidate_ids'}:
            raise ValueError('Unknown generate field')
        if request.get('type') != 'generate':
            raise ValueError('Expected generate or result')
        messages = request.get('messages')
        if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
            raise ValueError('messages must be a nonempty chat array, at most 64 messages')
        for m in messages:
            if not isinstance(m, dict) or set(m) != {'role', 'content'} or m['role'] not in (
                    'system', 'user', 'assistant') or type(m['content']) is not str:
                raise ValueError('Each message needs string role/content; no tools or templates')
        maximum = request.get('max_new_tokens')
        if type(maximum) is not int or not 1 <= maximum <= 512:
            raise ValueError('max_new_tokens must be an integer in [1,512]')
        declared = request.get('candidate_ids', [])
        if not isinstance(declared, list) or any(type(d) is not str for d in declared) or (
                len(declared) != len(set(declared)) or not set(declared) <= candidate_ids):
            raise ValueError('candidate_ids must be distinct IDs from this query')
        labels = request.get('logprob_tokens', [])
        if not isinstance(labels, list) or len(labels) > 32 or any(type(s) is not str for s in labels):
            raise ValueError('At most 32 single-token logprob strings are allowed')
        label_ids = {}
        for label in labels:
            ids = self.tokenizer.encode(label, add_special_tokens=False)
            if len(ids) != 1:
                raise ValueError('logprob_tokens entries must each encode as one token')
            label_ids[label] = ids[0]
        ids = self.tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, enable_thinking=False, return_dict=False)
        # v5 tokenizers return BatchEncoding unless return_dict=False is explicit.
        if isinstance(ids, dict) or hasattr(ids, 'keys'):
            ids = ids['input_ids']
        return ids, maximum, label_ids, declared

    def generate(self, prepared, meter, on_reserve=lambda record: None):
        ids, maximum, labels, declared = prepared
        record = meter.reserve(len(ids), maximum)
        record['declared_candidate_ids'] = declared
        on_reserve(record)
        started = time.monotonic()
        torch = self.torch
        try:
            inputs = torch.tensor([ids], device='cuda', dtype=torch.long)
            with torch.inference_mode():
                result = self.model.generate(inputs, max_new_tokens=maximum,
                    do_sample=False, use_cache=True, return_dict_in_generate=True,
                    output_scores=bool(labels),
                    eos_token_id=self.tokenizer.eos_token_id,
                    pad_token_id=self.tokenizer.eos_token_id)
            output = result.sequences[0, len(ids):].tolist()
            logprobs = {}
            if labels:
                values = torch.log_softmax(result.scores[0][0].float(), dim=-1)
                logprobs = {s: float(values[i]) for s, i in labels.items()}
                if not all(math.isfinite(v) for v in logprobs.values()):
                    raise RuntimeError('Nonfinite logits')
            meter.settle(record, len(output))  # EOS and special output tokens count.
            return {'type': 'generation', 'text': self.tokenizer.decode(output,
                        skip_special_tokens=True), 'input_tokens': len(ids),
                    'output_tokens': len(output), 'spent_tokens': meter.spent,
                    'remaining_tokens': meter.budget - meter.spent,
                    'first_token_logprobs': logprobs}
        except Exception:
            # An executed failed request retains its full reservation; never free retries.
            record['status'] = 'failed'
            raise
        finally:
            record['inference_seconds'] = time.monotonic() - started
            self.info['peak_allocated_bytes'] = torch.cuda.max_memory_allocated()
            self.info['peak_reserved_bytes'] = torch.cuda.max_memory_reserved()
