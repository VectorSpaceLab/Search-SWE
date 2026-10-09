#!/usr/bin/env python3
"""Build the starter's disk-backed document store."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def document_id(record: dict, line_number: int) -> str:
    value = record.get("_id", record.get("doc_id", record.get("id")))
    if value is None or not str(value):
        raise ValueError(f"corpus line {line_number}: missing document ID")
    return str(value)


def document_text(record: dict, line_number: int) -> str:
    text = record.get("text", "")
    title = record.get("title", "")
    if text is not None and not isinstance(text, str):
        raise ValueError(f"corpus line {line_number}: text must be a string")
    if title is not None and not isinstance(title, str):
        raise ValueError(f"corpus line {line_number}: title must be a string")
    parts = [part.strip() for part in (title or "", text or "") if part.strip()]
    if not parts:
        raise ValueError(f"corpus line {line_number}: title and text are both empty")
    return "\n\n".join(parts)


def build(corpus: Path, index_dir: Path) -> int:
    index_dir.mkdir(parents=True, exist_ok=True)
    database_path = index_dir / "documents.sqlite3"
    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute(
        "CREATE TABLE documents (doc_id TEXT PRIMARY KEY, text TEXT NOT NULL)"
    )

    count = 0
    batch: list[tuple[str, str]] = []
    try:
        with corpus.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(
                        f"corpus line {line_number}: record must be an object"
                    )
                batch.append(
                    (
                        document_id(record, line_number),
                        document_text(record, line_number),
                    )
                )
                if len(batch) >= 1000:
                    connection.executemany(
                        "INSERT INTO documents(doc_id, text) VALUES (?, ?)", batch
                    )
                    count += len(batch)
                    batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO documents(doc_id, text) VALUES (?, ?)", batch
            )
            count += len(batch)
        connection.commit()
    finally:
        connection.close()

    if count == 0:
        raise ValueError("corpus is empty")
    (index_dir / "index.json").write_text(
        json.dumps({"document_count": count}) + "\n", encoding="utf-8"
    )
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    args = parser.parse_args()
    count = build(args.corpus, args.index_dir)
    print(json.dumps({"document_count": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
