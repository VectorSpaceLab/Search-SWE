#!/usr/bin/env python3
"""Prefix-truncation Cross-Encoder reranking server."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Sequence


MAX_LENGTH = 512
MAX_CANDIDATES = 100
DEFAULT_BATCH_SIZE = 16


class CrossEncoder:
    def __init__(self, model_path: str) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, use_fast=True, local_files_only=True
        )
        dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, dtype=dtype, local_files_only=True
        ).to(self.device).eval()

    def score(
        self,
        query: str,
        document_tokens: Sequence[Sequence[int]],
        batch_size: int = 32,
    ) -> list[float]:
        values: list[float] = []
        query_ids = self.tokenizer(
            query, add_special_tokens=False, truncation=True, max_length=MAX_LENGTH
        )["input_ids"]
        payload_length = MAX_LENGTH - 4
        for start in range(0, len(document_tokens), batch_size):
            sequences: list[list[int]] = []
            for raw_document_ids in document_tokens[start : start + batch_size]:
                document_ids = list(raw_document_ids)
                query_length = min(len(query_ids), payload_length)
                document_length = min(len(document_ids), payload_length)
                overflow = query_length + document_length - payload_length
                if overflow > 0:
                    removed = min(overflow, document_length)
                    document_length -= removed
                    overflow -= removed
                    if overflow > 0:
                        query_length = max(0, query_length - overflow)
                sequences.append(
                    [
                        self.tokenizer.bos_token_id,
                        *query_ids[:query_length],
                        self.tokenizer.eos_token_id,
                        self.tokenizer.eos_token_id,
                        *document_ids[:document_length],
                        self.tokenizer.eos_token_id,
                    ]
                )

            width = max(len(sequence) for sequence in sequences)
            input_ids = self.torch.full(
                (len(sequences), width),
                self.tokenizer.pad_token_id,
                dtype=self.torch.long,
                device=self.device,
            )
            attention_mask = self.torch.zeros(
                (len(sequences), width),
                dtype=self.torch.long,
                device=self.device,
            )
            for row, sequence in enumerate(sequences):
                length = len(sequence)
                input_ids[row, :length] = self.torch.tensor(
                    sequence, dtype=self.torch.long, device=self.device
                )
                attention_mask[row, :length] = 1

            with self.torch.inference_mode():
                logits = self.model(
                    input_ids=input_ids, attention_mask=attention_mask
                ).logits.reshape(-1)
            values.extend(float(value) for value in logits.float().cpu().tolist())
        return values


class Reranker:
    def __init__(self, index_dir: Path, model_path: str) -> None:
        self.connection = sqlite3.connect(
            index_dir / "documents.sqlite3", check_same_thread=False
        )
        self.cross_encoder = CrossEncoder(model_path)
        self.document_token_cache: dict[str, list[int]] = {}

    def document_tokens(self, doc_ids: Sequence[str]) -> list[list[int]]:
        tokenized: list[list[int]] = []
        for doc_id in doc_ids:
            cached = self.document_token_cache.get(doc_id)
            if cached is None:
                row = self.connection.execute(
                    "SELECT text FROM documents WHERE doc_id = ?", (doc_id,)
                ).fetchone()
                if row is None:
                    raise ValueError(f"candidate document is absent from corpus: {doc_id}")
                cached = list(
                    self.cross_encoder.tokenizer(
                        str(row[0]),
                        add_special_tokens=False,
                        truncation=True,
                        max_length=MAX_LENGTH,
                    )["input_ids"]
                )
                self.document_token_cache[doc_id] = cached
            tokenized.append(cached)
        return tokenized

    def rerank(
        self, query: dict[str, Any], top_k: int | None = None
    ) -> dict[str, Any]:
        query_id = query.get("query_id", query.get("_id"))
        text = query.get("text")
        candidates = query.get("bm25_top_100")
        if query_id is None or not str(query_id):
            raise ValueError("query_id is required")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("query text must be non-empty")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("candidates must be a non-empty list")
        if len(candidates) > MAX_CANDIDATES:
            raise ValueError(f"candidate pool exceeds {MAX_CANDIDATES}")

        doc_ids: list[str] = []
        seen: set[str] = set()
        for position, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict) or "doc_id" not in candidate:
                raise ValueError(f"candidate {position} must contain doc_id")
            doc_id = str(candidate["doc_id"])
            if not doc_id or doc_id in seen:
                raise ValueError(f"candidate {position} has an empty or duplicate ID")
            seen.add(doc_id)
            doc_ids.append(doc_id)

        if top_k is None:
            top_k = len(doc_ids)
        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or not 1 <= top_k <= len(doc_ids)
        ):
            raise ValueError(
                f"top_k must be an integer between 1 and {len(doc_ids)}"
            )

        document_tokens = self.document_tokens(doc_ids)
        scores = self.cross_encoder.score(text, document_tokens)
        if len(scores) != len(doc_ids) or not all(math.isfinite(x) for x in scores):
            raise RuntimeError("Cross-Encoder produced invalid scores")
        # Python's sort is stable, so equal scores retain the original
        # candidate order supplied by the query.
        ranked = sorted(zip(doc_ids, scores), key=lambda item: -item[1])
        return {
            "query_id": str(query_id),
            "results": [
                {"doc_id": doc_id, "score": score}
                for doc_id, score in ranked[:top_k]
            ],
        }


def handler_for(reranker: Reranker):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self.send_json(200, {"status": "ok"})
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/rerank":
                self.send_json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                query = request.get("query")
                if not isinstance(query, dict):
                    raise ValueError("request.query must be an object")
                self.send_json(200, reranker.rerank(query, request.get("top_k")))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.send_json(500, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    reranker = Reranker(args.index_dir, args.model)
    server = HTTPServer(("127.0.0.1", 0), handler_for(reranker))
    host, port = server.server_address
    (args.index_dir / "service.json").write_text(
        json.dumps({"host": host, "port": port}) + "\n", encoding="utf-8"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
