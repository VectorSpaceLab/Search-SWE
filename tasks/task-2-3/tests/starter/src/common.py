from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from FlagEmbedding import FlagLLMModel


QUERY_MODEL_PATH = Path("/task/models/Qwen3-Embedding-4B")
QUERY_INSTRUCTION = "Given a claim, find documents that refute the claim."
QUERY_MAX_LENGTH = 512


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    if not rows:
        raise ValueError(f"{path}: no records")
    return rows


def query_id(row: dict[str, Any]) -> str:
    value = row.get("query_id", row.get("_id"))
    if value is None or not str(value):
        raise ValueError("query is missing query_id or _id")
    return str(value)


def query_text(row: dict[str, Any]) -> str:
    value = row.get("text")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query text is empty")
    return value


def encode_queries(
    texts: list[str],
    batch_size: int = 8,
) -> np.ndarray:
    if not texts:
        raise ValueError("cannot encode an empty query list")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = FlagLLMModel(
        str(QUERY_MODEL_PATH),
        use_fp16=False,
        use_bf16=True,
        query_instruction_for_retrieval=QUERY_INSTRUCTION,
        query_instruction_format="Instruct: {}\nQuery:{}",
        pooling_method="last_token",
        devices=device,
        batch_size=batch_size,
        query_max_length=QUERY_MAX_LENGTH,
        convert_to_numpy=True,
    )
    embeddings = np.asarray(
        model.encode_queries(
            texts,
            batch_size=batch_size,
            max_length=QUERY_MAX_LENGTH,
            convert_to_numpy=True,
        ),
        dtype=np.float32,
    )
    if embeddings.ndim == 1:
        embeddings = embeddings[None, :]
    if embeddings.shape != (len(texts), 2560):
        raise ValueError(f"unexpected query embedding shape: {embeddings.shape}")
    return embeddings
