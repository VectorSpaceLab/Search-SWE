#!/usr/bin/env python3
"""Evaluate a submitted code embedder checkpoint against its unmodified backbone."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


BACKBONE_PATH = Path("/task/models/bge-base-en-v1.5")
MODEL_PATH = Path("/app/submission/model")
CORPUS_PATH = Path("/task/data/corpus.jsonl")
QUERIES_PATH = Path("/tests/data/queries.jsonl")
GROUND_TRUTH_PATH = Path("/tests/data/ground_truth.jsonl")
REPORT_PATH = Path("/logs/verifier/task-2-2-eval/evaluation.json")
MAX_LENGTH = 512
BATCH_SIZE = 32

_NON_STRUCTURAL_CONFIG_FIELDS = {
    "_name_or_path",
    "finetuning_task",
    "id2label",
    "label2id",
    "problem_type",
    "torch_dtype",
    "transformers_version",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no records")
    return rows


def required_text(row: dict[str, Any], field: str, location: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: missing non-empty {field!r}")
    return value.strip()


def document_text(row: dict[str, Any], location: str) -> str:
    text = f"{row.get('title', '')} {row.get('text', '')}".strip()
    if not text:
        raise ValueError(f"{location}: empty document text")
    return text


def load_evaluation_data() -> tuple[list[str], list[str], list[str], list[str], dict[str, set[str]]]:
    corpus_rows = read_jsonl(CORPUS_PATH)
    corpus_ids = [required_text(row, "_id", f"{CORPUS_PATH}:{index}") for index, row in enumerate(corpus_rows, 1)]
    if len(set(corpus_ids)) != len(corpus_ids):
        raise ValueError("corpus contains duplicate document IDs")
    corpus_texts = [document_text(row, f"{CORPUS_PATH}:{index}") for index, row in enumerate(corpus_rows, 1)]
    corpus_id_set = set(corpus_ids)

    query_rows = read_jsonl(QUERIES_PATH)
    query_ids = [required_text(row, "_id", f"{QUERIES_PATH}:{index}") for index, row in enumerate(query_rows, 1)]
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("queries contain duplicate query IDs")
    query_texts = [required_text(row, "text", f"{QUERIES_PATH}:{index}") for index, row in enumerate(query_rows, 1)]

    labels: dict[str, set[str]] = {}
    for index, row in enumerate(read_jsonl(GROUND_TRUTH_PATH), 1):
        query_id = required_text(row, "query_id", f"{GROUND_TRUTH_PATH}:{index}")
        doc_ids = row.get("relevant_doc_ids")
        if not isinstance(doc_ids, list) or not doc_ids or not all(isinstance(doc_id, str) and doc_id for doc_id in doc_ids):
            raise ValueError(f"{GROUND_TRUTH_PATH}:{index}: invalid relevant_doc_ids")
        if query_id in labels:
            raise ValueError(f"{GROUND_TRUTH_PATH}:{index}: duplicate query ID")
        labels[query_id] = set(doc_ids)

    if set(query_ids) != set(labels):
        raise ValueError("queries and ground truth do not cover the same query IDs")
    unknown_docs = set().union(*labels.values()) - corpus_id_set
    if unknown_docs:
        raise ValueError(f"ground truth references documents outside the corpus: {sorted(unknown_docs)[:3]}")
    return corpus_ids, corpus_texts, query_ids, query_texts, labels


def config_signature(model: torch.nn.Module) -> dict[str, Any]:
    config = model.config.to_dict()
    for field in _NON_STRUCTURAL_CONFIG_FIELDS:
        config.pop(field, None)
    return config


def model_signature(model: torch.nn.Module) -> dict[str, Any]:
    return {
        "model_class": f"{type(model).__module__}.{type(model).__qualname__}",
        "config": config_signature(model),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "parameters": [(name, tuple(parameter.shape)) for name, parameter in model.named_parameters()],
    }


def require_matching_architecture(backbone: torch.nn.Module, submitted: torch.nn.Module) -> int:
    expected = model_signature(backbone)
    actual = model_signature(submitted)
    for field in ("model_class", "config", "parameter_count", "parameters"):
        if actual[field] != expected[field]:
            raise ValueError(f"submitted checkpoint does not match the backbone {field}")
    return int(expected["parameter_count"])


def load_checkpoint(path: Path) -> tuple[Any, torch.nn.Module]:
    if not path.is_dir():
        raise FileNotFoundError(f"missing checkpoint directory: {path}")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    return tokenizer, model


def encode(model: torch.nn.Module, tokenizer: Any, texts: list[str], device: torch.device) -> np.ndarray:
    vectors: list[np.ndarray] = []
    model.eval().to(device)
    with torch.inference_mode():
        for start in range(0, len(texts), BATCH_SIZE):
            encoded = tokenizer(
                texts[start : start + BATCH_SIZE],
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )
            encoded = {name: value.to(device) for name, value in encoded.items()}
            embeddings = model(**encoded).last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            vectors.append(embeddings.float().cpu().numpy())
    return np.concatenate(vectors, axis=0)


def accuracy_at_1(
    model: torch.nn.Module,
    tokenizer: Any,
    corpus_texts: list[str],
    corpus_ids: list[str],
    query_texts: list[str],
    query_ids: list[str],
    labels: dict[str, set[str]],
    device: torch.device,
) -> float:
    corpus_vectors = encode(model, tokenizer, corpus_texts, device)
    query_vectors = encode(model, tokenizer, query_texts, device)
    predicted_indexes = np.argmax(query_vectors @ corpus_vectors.T, axis=1)
    hits = sum(corpus_ids[int(index)] in labels[query_id] for index, query_id in zip(predicted_indexes, query_ids))
    return hits / len(query_ids)


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    corpus_ids, corpus_texts, query_ids, query_texts, labels = load_evaluation_data()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    backbone_tokenizer, backbone = load_checkpoint(BACKBONE_PATH)
    submitted_tokenizer, submitted = load_checkpoint(MODEL_PATH)
    parameter_count = require_matching_architecture(backbone, submitted)

    baseline_accuracy = accuracy_at_1(
        backbone,
        backbone_tokenizer,
        corpus_texts,
        corpus_ids,
        query_texts,
        query_ids,
        labels,
        device,
    )
    del backbone, backbone_tokenizer
    if device.type == "cuda":
        torch.cuda.empty_cache()

    submitted_accuracy = accuracy_at_1(
        submitted,
        submitted_tokenizer,
        corpus_texts,
        corpus_ids,
        query_texts,
        query_ids,
        labels,
        device,
    )
    improvement = submitted_accuracy - baseline_accuracy
    if not all(math.isfinite(value) for value in (baseline_accuracy, submitted_accuracy, improvement)):
        raise ValueError("non-finite evaluation result")
    report = {
        "valid": True,
        "dataset": "code-retrieval",
        "split": "test",
        "metric": "Accuracy@1",
        "query_count": len(query_ids),
        "backbone_parameter_count": parameter_count,
        "baseline_accuracy@1": baseline_accuracy,
        "submitted_accuracy@1": submitted_accuracy,
        "improvement": improvement,
        "reward": max(0.0, min(1.0, improvement)),
    }
    write_report(report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report = {"valid": False, "reward": 0.0, "error": f"{type(error).__name__}: {error}"}
        write_report(report)
        print(report["error"], file=sys.stderr)
        raise SystemExit(1)
