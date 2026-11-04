"""Fixed retrieval semantics shared by the two public reference runners."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import numpy as np

VECTOR_SHA256 = "54c2f4a5a83e43d8ab5569f195c7e478a0807c9018e0749a9f62158656c8cd46"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected nonempty JSONL objects")
    return rows


def row_id(row):
    for key in ("query_id", "id", "_id", "doc_id"):
        if row.get(key) is not None and str(row[key]):
            return str(row[key])
    raise ValueError("missing ID")


def canonical_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty text")
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def exclusions(corpus, queries):
    by_text = {}
    ids = {row_id(row) for row in corpus}
    for row in corpus:
        by_text.setdefault(canonical_text(row["text"]), set()).add(row_id(row))
    return {
        row_id(q): by_text.get(canonical_text(q["text"]), set()) | ({row_id(q)} & ids)
        for q in queries
    }


def rank_scores(scores, corpus, queries, top_k=1):
    """Full ranking before filtering ensures refill and corpus-order ties."""
    ids = [row_id(row) for row in corpus]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate corpus IDs")
    scores = np.asarray(scores)
    if scores.shape != (len(queries), len(corpus)) or not np.isfinite(scores).all():
        raise ValueError("invalid score matrix")
    if top_k < 1:
        raise ValueError("top-k must be positive")
    blocked = exclusions(corpus, queries)
    output = []
    for q, values in zip(queries, scores):
        ranked = [int(i) for i in np.argsort(-values, kind="stable")
                  if ids[int(i)] not in blocked[row_id(q)]][:top_k]
        if len(ranked) != top_k:
            raise ValueError("insufficient eligible documents")
        output.append({"query_id": row_id(q), "results": [
            {"doc_id": ids[i], "score": float(values[i])} for i in ranked]})
    return output


def load_vectors(path, corpus):
    if sha256(path) != VECTOR_SHA256:
        raise ValueError("fixed vector checksum mismatch")
    vectors = np.load(path, mmap_mode="r", allow_pickle=False)
    if vectors.shape != (len(corpus), 2560) or vectors.dtype != np.float32:
        raise ValueError("fixed vector shape/dtype mismatch")
    if not np.isfinite(vectors).all():
        raise ValueError("nonfinite fixed vectors")
    return vectors
