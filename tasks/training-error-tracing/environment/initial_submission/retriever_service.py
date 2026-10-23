#!/usr/bin/env python3
"""Persistent training-data retriever with layer-streamed fixed-probe inference."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import socketserver
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from safetensors import safe_open
from transformers import AutoConfig, AutoModel
from accelerate import init_empty_weights
from bitsandbytes.nn import Linear4bit, Params4bit

sys.path.insert(0, "/task/tools")
from candidate_features import entity_pattern
from retrieval_index import Retriever
from source_coherence import token_surface
from lexical_source import _token_set
from token_contract import MAX_LENGTH, prompt_text


class StreamedProbe:
    """Rebuild the unchanged NF4 decoder on CPU and stream one block to CUDA."""

    def __init__(self, base: Path):
        if torch.cuda.device_count() != 1:
            raise RuntimeError("The fixed probe expects the assigned single GPU")
        self.base = base
        self.device = torch.device("cuda")
        metadata = json.loads((base / "probe.json").read_text())
        self.config = AutoConfig.from_pretrained(base, local_files_only=True)
        if self.config.num_hidden_layers != metadata["layers"]:
            raise ValueError("Probe layer count differs from its configuration")
        self.config.use_cache = False
        self.config._attn_implementation = "sdpa"

        with init_empty_weights(include_buffers=False):
            model = AutoModel.from_config(
                self.config,
                attn_implementation="sdpa",
                dtype=torch.bfloat16,
            )
        self._replace_linears(model)
        self._load_state(model)
        model.eval()
        model.requires_grad_(False)
        model.config.use_cache = False
        self.model = model
        self.hidden_size = int(model.config.hidden_size)

        # Keep the small final normalization and rotary tables resident.
        self.model.norm.to(self.device)
        self.model.rotary_emb.to(self.device)
        self._install_stream_hooks()
        self._warm_kernels()

    @staticmethod
    def _replace_linears(module):
        for name, child in list(module.named_children()):
            if isinstance(child, nn.Linear):
                replacement = Linear4bit(
                    child.in_features,
                    child.out_features,
                    bias=child.bias is not None,
                    compute_dtype=torch.bfloat16,
                    compress_statistics=True,
                    quant_type="nf4",
                    quant_storage=torch.uint8,
                    device="meta",
                )
                setattr(module, name, replacement)
            else:
                StreamedProbe._replace_linears(child)

    def _load_state(self, model):
        path = self.base / "model.safetensors"
        with safe_open(path, framework="pt", device="cpu") as source:
            keys = set(source.keys())
            model.embed_tokens.weight = nn.Parameter(
                source.get_tensor("model.embed_tokens.weight"), requires_grad=False
            )
            model.norm.weight = nn.Parameter(
                source.get_tensor("model.norm.weight"), requires_grad=False
            )

            for layer_index, layer in enumerate(model.layers):
                for module_name, module in layer.named_modules():
                    if not module_name:
                        continue
                    prefix = f"model.layers.{layer_index}.{module_name}"
                    if isinstance(module, Linear4bit):
                        weight_key = prefix + ".weight"
                        quantized_stats = {}
                        for suffix in (
                            "absmax",
                            "nested_absmax",
                            "nested_quant_map",
                            "quant_map",
                            "quant_state.bitsandbytes__nf4",
                        ):
                            key = weight_key + "." + suffix
                            if key in keys:
                                quantized_stats["weight." + suffix] = source.get_tensor(key)
                        if len(quantized_stats) != 5:
                            raise ValueError(f"Incomplete NF4 state for {weight_key}")
                        module.weight = Params4bit.from_prequantized(
                            source.get_tensor(weight_key),
                            quantized_stats=quantized_stats,
                            requires_grad=False,
                            device="cpu",
                            module=module,
                        )
                        if module.bias is not None:
                            bias_key = prefix + ".bias"
                            module.bias = nn.Parameter(
                                source.get_tensor(bias_key), requires_grad=False
                            )
                    else:
                        for parameter_name, parameter in list(
                            module.named_parameters(recurse=False)
                        ):
                            key = prefix + "." + parameter_name
                            if key not in keys:
                                raise ValueError(f"Missing fixed probe parameter: {key}")
                            module._parameters[parameter_name] = nn.Parameter(
                                source.get_tensor(key), requires_grad=False
                            )

        meta_parameters = [
            name for name, parameter in model.named_parameters() if parameter.is_meta
        ]
        if meta_parameters:
            raise ValueError("Unrestored fixed probe parameters: " + ", ".join(meta_parameters[:8]))
        for module in model.modules():
            if isinstance(module, Linear4bit) and module.weight.quant_state is None:
                raise ValueError("An NF4 linear layer has no serialized quantization state")

    @staticmethod
    def _pin_quant_state(state):
        for name in ("absmax", "code", "offset"):
            tensor = getattr(state, name, None)
            if isinstance(tensor, torch.Tensor) and tensor.device.type == "cpu" and not tensor.is_pinned():
                setattr(state, name, tensor.pin_memory())
        nested = getattr(state, "state2", None)
        if nested is not None:
            StreamedProbe._pin_quant_state(nested)
        return state

    @staticmethod
    def _snapshot_layer(layer):
        saved = []
        for submodule in layer.modules():
            for name, parameter in list(submodule._parameters.items()):
                if parameter is None:
                    continue
                if isinstance(parameter, Params4bit):
                    if not parameter.data.is_pinned():
                        parameter.data = parameter.data.pin_memory()
                    StreamedProbe._pin_quant_state(parameter.quant_state)
                    cpu_quant_state = StreamedProbe._pin_quant_state(
                        copy.deepcopy(parameter.quant_state)
                    )
                    saved.append(
                        (
                            submodule,
                            name,
                            "nf4",
                            parameter,
                            parameter.data,
                            cpu_quant_state,
                        )
                    )
                else:
                    cpu_parameter = nn.Parameter(
                        parameter.detach().to("cpu").clone(),
                        requires_grad=parameter.requires_grad,
                    )
                    saved.append((submodule, name, "plain", cpu_parameter, None, None))
        return saved

    def _install_stream_hooks(self):
        self._cpu_snapshots = {
            layer: self._snapshot_layer(layer) for layer in self.model.layers
        }
        self._hook_handles = []
        for layer in self.model.layers:
            self._hook_handles.append(
                layer.register_forward_pre_hook(self._move_layer_to_gpu, with_kwargs=True)
            )
            self._hook_handles.append(
                layer.register_forward_hook(
                    self._restore_layer_to_cpu,
                    with_kwargs=True,
                    always_call=True,
                )
            )

    def _move_layer_to_gpu(self, layer, args, kwargs):
        layer.to(self.device, non_blocking=True)
        return args, kwargs

    def _restore_layer_to_cpu(self, layer, args, kwargs, output):
        for submodule, name, kind, parameter, data, quant_state in self._cpu_snapshots[layer]:
            if kind == "nf4":
                # Params4bit.to(cuda) returns a GPU wrapper but mutates its original
                # QuantState. Restore the independent CPU state and original packed data.
                parameter.data = data
                parameter.quant_state = quant_state
                parameter.bnb_quantized = True
                submodule._parameters[name] = parameter
                submodule.quant_state = quant_state
            else:
                submodule._parameters[name] = parameter
        return output

    def _warm_kernels(self):
        # Initialize CUDA and the fixed NF4 kernels without using any query data.
        embeddings = torch.zeros(
            (1, 64, self.hidden_size), dtype=torch.bfloat16, device=self.device
        )
        mask = torch.ones((1, 64), dtype=torch.long, device=self.device)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            self.model(inputs_embeds=embeddings, attention_mask=mask, use_cache=False)
            torch.cuda.synchronize()
        del embeddings, mask

class CachedTrainingFeatures:
    """Training-only pools using precomputed tokenizer offsets for each row."""

    def __init__(self, original):
        self.rows = original.rows
        self.tokenizer = original.tokenizer
        self.base_nll = original.base_nll
        self.trained_loss = original.trained_loss
        self.row_words = original.row_words
        self.pool_cache = {}
        self.pattern_cache = {}
        self.prompt_lengths = np.empty(len(self.rows), dtype=np.int32)
        self.answer_lengths = np.empty(len(self.rows), dtype=np.int32)
        self.offsets = [None] * len(self.rows)
        self._precompute_offsets()

    def _precompute_offsets(self):
        prompts = [prompt_text(row["instruction"], row["input"]) for row in self.rows]
        outputs = [row["output"] for row in self.rows]
        batch_size = 256
        for start in range(0, len(self.rows), batch_size):
            stop = min(start + batch_size, len(self.rows))
            prompt_batch = self.tokenizer(
                prompts[start:stop], add_special_tokens=False, padding=False
            )["input_ids"]
            output_batch = self.tokenizer(
                outputs[start:stop],
                add_special_tokens=False,
                padding=False,
                return_offsets_mapping=True,
            )
            for offset, index in enumerate(range(start, stop)):
                prompt_length = len(prompt_batch[offset])
                encoded_ids = output_batch["input_ids"][offset]
                available = max(0, MAX_LENGTH - prompt_length)
                token_offsets = np.asarray(
                    output_batch["offset_mapping"][offset][:available], dtype=np.int32
                ).reshape(-1, 2)
                self.prompt_lengths[index] = prompt_length
                self.answer_lengths[index] = len(encoded_ids)
                self.offsets[index] = token_offsets

    def pattern(self, target):
        key = target.strip().casefold()
        if key not in self.pattern_cache:
            self.pattern_cache[key] = entity_pattern(target)
        return self.pattern_cache[key]

    def positions(self, index, target):
        row = self.rows[index]
        pattern = self.pattern(target)
        matches = list(pattern.finditer(row["output"]))
        offsets = self.offsets[index]
        end_of_retained = int(offsets[:, 1].max()) if len(offsets) else 0
        prompt_length = int(self.prompt_lengths[index])
        positions = set()
        for match in matches:
            if match.end() <= end_of_retained:
                for token_index, (start, end) in enumerate(offsets):
                    if start < match.end() and end > match.start():
                        positions.add(prompt_length + token_index)
        return sorted(positions), len(matches), int(self.answer_lengths[index])

    def pool(self, target):
        key = target.strip().casefold()
        if key in self.pool_cache:
            return self.pool_cache[key]
        pattern = self.pattern(target)
        indices = []
        features = []
        for index, row in enumerate(self.rows):
            if not pattern.search(row["output"]):
                continue
            positions, count, answer_length = self.positions(index, target)
            nll = (
                self.base_nll[index, positions].astype(np.float32)
                if self.base_nll is not None and positions
                else np.array([0.0], dtype=np.float32)
            )
            indices.append(index)
            features.append(
                [
                    math.log1p(count),
                    float(bool(pattern.search(row["instruction"] + "\n" + row["input"]))),
                    math.log1p(answer_length),
                    float(bool(positions)),
                    float(nll.mean()),
                    float(nll.max()),
                    float(self.trained_loss[index]) if self.trained_loss is not None else 0.0,
                ]
            )
        result = (
            np.asarray(indices, dtype=np.int64),
            np.asarray(features, dtype=np.float32).reshape(-1, 7),
        )
        self.pool_cache[key] = result
        return result


class CachedSourceCoherence:
    """Source-alternative cohorts built from the same cached training offsets."""

    def __init__(self, training, alternatives):
        self.training = training
        self.alternatives = alternatives
        self.cache = {}
        self.decoded = {}

    def pool(self, target):
        key = target.strip().casefold()
        if key in self.cache:
            return self.cache[key]
        indices, fixed = self.training.pool(target)
        surfaces = []
        for index in indices:
            positions, _, _ = self.training.positions(int(index), target)
            surface = ""
            if positions:
                nll = self.training.base_nll[int(index), positions]
                position = positions[int(np.argmax(nll))]
                token_id = int(self.alternatives[int(index), position])
                if token_id >= 0:
                    if token_id not in self.decoded:
                        self.decoded[token_id] = token_surface(
                            self.training.tokenizer.decode([token_id])
                        )
                    surface = self.decoded[token_id]
            surfaces.append(surface)
        counts = Counter(surface for surface in surfaces if surface)
        mode = min(counts, key=lambda surface: (-counts[surface], surface)) if counts else None
        frequency = np.asarray(
            [math.log1p(counts[surface]) if surface else -1e6 for surface in surfaces],
            dtype=np.float64,
        )
        mode_match = np.asarray(
            [float(bool(surface) and surface == mode) for surface in surfaces],
            dtype=np.float64,
        )
        result = {
            "indices": indices,
            "surfaces": surfaces,
            "counts": dict(counts),
            "mode": mode,
            "source-mode": mode_match * 1e6 + fixed[:, 5] - (1 - fixed[:, 3]) * 1e7,
            "source-frequency": frequency + 0.1 * fixed[:, 5] - (1 - fixed[:, 3]) * 1e7,
        }
        self.cache[key] = result
        return result


class TrainingRetriever:
    def __init__(self, data_dir: Path, model_dir: Path, index_dir: Path):
        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.index_dir = index_dir
        args = SimpleNamespace(
            mode="source-mode",
            data_dir=data_dir,
            model_dir=model_dir,
            base_nll=data_dir / "base-nll/base-token-nll.npz",
            base_alternatives=data_dir / "base-alternatives/base-token-alternatives.npz",
            ranker=None,
        )
        self.index = Retriever(args)
        self.rows = self.index.rows
        self.ids = self.index.ids
        self.id_order = np.asarray(self.ids)
        if self.index.coherence is None or self.index.base_nll is None:
            raise ValueError("Training-only NLL and alternative arrays are required")
        original_training = self.index.training
        alternatives = self.index.coherence.alternatives
        self.training = CachedTrainingFeatures(original_training)
        self.coherence = CachedSourceCoherence(self.training, alternatives)
        self.index.training = self.training
        self.index.coherence = self.coherence

        self.doc_terms = [
            _token_set(row["instruction"] + " " + row["input"] + " " + row["output"])
            for row in self.rows
        ]
        document_frequency = Counter()
        for terms in self.doc_terms:
            document_frequency.update(terms)
        count = len(self.doc_terms)
        self.idf = {
            term: math.log((count + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }

        self.probe = StreamedProbe(model_dir / "base")
        self._load_head(model_dir / "base")
        self.head_pools = {}

    def _load_head(self, base):
        metadata = json.loads((base / "probe.json").read_text())
        with np.load(base / "output-head.npz", allow_pickle=False) as packed:
            token_ids = packed["token_ids"].astype(np.int64, copy=True)
            weights = packed["weights_bf16"]
            cpu_output = torch.from_numpy(weights).view(torch.bfloat16)
        if (
            len(token_ids) != metadata["head_rows"]
            or np.any(np.diff(token_ids) <= 0)
            or cpu_output.shape != (metadata["head_rows"], self.probe.hidden_size)
        ):
            raise ValueError("Invalid supplied fixed diagnostic output rows")

        decoded = self.training.tokenizer.batch_decode(
            [[int(token_id)] for token_id in token_ids],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        surfaces = [token_surface(text) for text in decoded]
        rows_by_surface = defaultdict(list)
        for row_index, surface in enumerate(surfaces):
            if surface:
                rows_by_surface[surface].append(row_index)

        self.output_token_ids = token_ids
        self.cpu_output = cpu_output
        self.output_surfaces = surfaces
        self.output_rows_by_surface = dict(rows_by_surface)
        self.token_id_to_head_row = np.full(
            self.probe.config.vocab_size, -1, dtype=np.int32
        )
        self.token_id_to_head_row[token_ids] = np.arange(len(token_ids), dtype=np.int32)

    def _lexical_choice(self, query, pool):
        query_terms = (
            _token_set(query["instruction"] + " " + query["input"])
            - _token_set(query["target_text"])
        )
        query_terms.intersection_update(self.idf)
        if not query_terms:
            return None

        row_scores = np.zeros(len(pool["indices"]), dtype=np.float32)
        surface_terms = defaultdict(set)
        surface_positions = defaultdict(list)
        for position, (index, surface) in enumerate(
            zip(pool["indices"], pool["surfaces"])
        ):
            if surface:
                surface_positions[surface].append(position)
            hits = query_terms.intersection(self.doc_terms[int(index)])
            if not hits:
                continue
            row_scores[position] = sum(self.idf[word] for word in hits)
            surface_terms[surface].update(
                word for word in hits if self.idf[word] >= 3.0
            )

        aggregates = {}
        for surface, positions in surface_positions.items():
            values = sorted((float(row_scores[j]) for j in positions), reverse=True)
            aggregates[surface] = sum(values[:3])
        if not aggregates:
            return None

        ranked = sorted(aggregates, key=lambda surface: (-aggregates[surface], surface))
        best = ranked[0]
        next_score = aggregates[ranked[1]] if len(ranked) > 1 else 0.0
        positions = surface_positions[best]
        if (
            len(surface_terms[best]) < 1
            or len(positions) < 10
            or aggregates[best] < 1.0
            or aggregates[best] < 1.12 * max(next_score, 1e-6)
        ):
            return None

        indices = pool["indices"]
        _, fixed = self.training.pool(query["target_text"])
        positions.sort(
            key=lambda j: (
                -float(row_scores[j]),
                -float(fixed[j][5]),
                self.ids[int(indices[j])],
            )
        )
        return [self.ids[int(indices[j])] for j in positions[:10]]

    def _head_pool(self, target, pool):
        key = target.strip().casefold()
        if key in self.head_pools:
            return self.head_pools[key]
        surfaces = {surface for surface in pool["counts"] if surface}
        row_indices = sorted(
            {
                row_index
                for surface in surfaces
                for row_index in self.output_rows_by_surface.get(surface, ())
            }
        )
        if not row_indices:
            raise ValueError("No supplied diagnostic rows cover the training alternatives")
        token_ids = self.output_token_ids[row_indices]
        rows = self.cpu_output[torch.as_tensor(row_indices, dtype=torch.long)].to(
            "cuda", dtype=torch.bfloat16
        )
        token_surfaces = tuple(self.output_surfaces[row_index] for row_index in row_indices)
        cached = (token_ids, rows, token_surfaces)
        self.head_pools[key] = cached
        return cached

    def _query_source_masses(self, query, pool):
        token_ids, rows, token_surfaces = self._head_pool(query["target_text"], pool)
        input_ids = np.asarray(query["input_ids"], dtype=np.int64)
        positions = np.asarray(query["target_token_indices"], dtype=np.int64)
        if (
            input_ids.ndim != 1
            or input_ids.size == 0
            or input_ids.size > 512
            or positions.ndim != 1
            or positions.size == 0
            or np.any(positions <= 0)
            or np.any(positions >= input_ids.size)
            or len(np.unique(positions)) != positions.size
        ):
            raise ValueError("Invalid supplied causal target positions")
        actual_ids = input_ids[positions]

        ids_cpu = torch.as_tensor(input_ids, dtype=torch.long, device="cpu").reshape(1, -1)
        embedded = F.embedding(ids_cpu, self.probe.model.embed_tokens.weight).to(
            "cuda", dtype=torch.bfloat16
        )
        mask = torch.ones_like(ids_cpu, device="cuda")
        position_tensor = torch.as_tensor(positions - 1, dtype=torch.long, device="cuda")
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            hidden = self.probe.model(
                inputs_embeds=embedded,
                attention_mask=mask,
                use_cache=False,
            ).last_hidden_state[0, position_tensor]
            logits = F.linear(hidden, rows).float()
            if len(positions) > 1:
                actual_head_rows = self.token_id_to_head_row[actual_ids]
                if np.any(actual_head_rows < 0):
                    raise ValueError("A marked target ID is outside the fixed diagnostic rows")
                actual_rows = self.cpu_output[
                    torch.as_tensor(actual_head_rows, dtype=torch.long)
                ].to("cuda", dtype=torch.bfloat16)
                actual_logits = (hidden.float() * actual_rows.float()).sum(-1)
                chosen = int((torch.logsumexp(logits, dim=1) - actual_logits).argmax())
            else:
                chosen = 0
            values = logits[chosen].softmax(-1).cpu().numpy()
        torch.cuda.synchronize()

        masses = defaultdict(float)
        for surface, value in zip(token_surfaces, values):
            if surface:
                masses[surface] += float(value)
        return masses

    def rank(self, query):
        if not isinstance(query, dict) or not isinstance(query.get("id"), str):
            raise ValueError("Malformed query object")
        pool = self.coherence.pool(query["target_text"])
        lexical = self._lexical_choice(query, pool)
        if lexical is not None:
            return {"query_id": query["id"], "ids": lexical}

        masses = self._query_source_masses(query, pool)
        indices = pool["indices"]
        _, fixed = self.training.pool(query["target_text"])
        scores = np.asarray(
            [masses.get(surface, 0.0) if surface else -1.0 for surface in pool["surfaces"]],
            dtype=np.float64,
        )
        # Diagnostic surface mass chooses the source cohort; training-only
        # target-token NLL breaks ties among records in that cohort.
        order = np.lexsort((self.id_order[indices], -fixed[:, 5], -scores))[:10]
        return {
            "query_id": query["id"],
            "ids": [self.ids[int(indices[i])] for i in order],
        }


def serve(args):
    retriever = TrainingRetriever(args.data_dir, args.model_dir, args.index_dir)
    socket_path = args.index_dir / "retriever.sock"
    socket_path.unlink(missing_ok=True)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                payload = json.loads(self.rfile.readline(1024 * 1024))
                if payload.get("action") != "query":
                    raise ValueError("Only query requests are supported")
                result = retriever.rank(payload["query"])
            except Exception as error:
                result = {"error": type(error).__name__ + ": " + str(error)}
            self.wfile.write((json.dumps(result, allow_nan=False) + "\n").encode("utf-8"))

    with socketserver.UnixStreamServer(str(socket_path), Handler) as server:
        (args.index_dir / "service.ready.json").write_text(
            json.dumps({"pid": os.getpid(), "method": "streamed-fixed-probe"}) + "\n"
        )
        server.serve_forever(poll_interval=0.05)


def prepare(args):
    args.index_dir.mkdir(parents=True, exist_ok=True)
    ready = args.index_dir / "service.ready.json"
    if ready.exists():
        raise ValueError("Use a fresh index directory")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        "--data-dir",
        str(args.data_dir.resolve()),
        "--model-dir",
        str(args.model_dir.resolve()),
        "--index-dir",
        str(args.index_dir.resolve()),
    ]
    with (args.index_dir / "service.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + 1700
    while not ready.exists():
        if process.poll() is not None:
            raise RuntimeError("Retriever service initialization failed; inspect INDEX/service.log")
        if time.monotonic() > deadline:
            process.terminate()
            raise TimeoutError("Retriever service initialization exceeded its budget")
        time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "serve"])
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args)
    else:
        serve(args)


if __name__ == "__main__":
    main()
