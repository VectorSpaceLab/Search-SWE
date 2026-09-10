#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np


FORMAT_VERSION = 3
TOP_K = 100
# The starter is the unpruned lookup baseline. Long-posting removal is
# available only as an explicit experiment through --max-df.
DEFAULT_MAX_DF = 0
DEFAULT_BLOCK_SIZE = 128
DEFAULT_BUCKET_COUNT = 64
RECORD = struct.Struct("<II")
RECORD_DTYPE = np.dtype([("term", "<u4"), ("doc", "<u4")])
TERM_META_DTYPE = np.dtype(
    [
        ("old_id", "<u4"),
        ("offset", "<u8"),
        ("length", "<u4"),
        ("block_offset", "<u8"),
        ("block_count", "<u4"),
        ("df", "<u4"),
        ("idf", "<f4"),
    ]
)
BUFFER_LIMIT = 256 * 1024


def load_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSON object expected at {path}:{line_number}")
            yield row


def parse_terms(row: dict[str, Any]) -> list[str]:
    raw_terms = row.get("terms", [])
    if not isinstance(raw_terms, list):
        raise ValueError("terms must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_terms:
        if isinstance(item, str):
            term = item
        elif isinstance(item, dict) and "term_id" in item and "weight" not in item:
            term = str(item["term_id"])
        else:
            raise ValueError("v0.3 input terms must be strings without weights")
        if not term or term in seen:
            raise ValueError(f"empty or duplicate term {term!r}")
        seen.add(term)
        result.append(term)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_stats_path(corpus: Path, explicit: Path | None) -> Path:
    candidate = explicit or corpus.parent / "validation" / "stats.json"
    if not candidate.is_file():
        raise FileNotFoundError(f"missing blind term statistics: {candidate}")
    return candidate


def load_term_statistics(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = json.loads(path.read_text(encoding="utf-8"))
    rows = root.get("term_stats")
    if not isinstance(rows, list) or not rows:
        raise ValueError("term_stats must be a non-empty list")
    normalized = []
    seen: set[str] = set()
    for old_id, row in enumerate(rows):
        term = str(row.get("term_id", ""))
        df = int(row.get("df", -1))
        if not term or term in seen or df < 0:
            raise ValueError(f"invalid term_stats row {old_id}")
        seen.add(term)
        normalized.append({"term_id": term, "df": df})
    return root, normalized


class BucketWriter:
    def __init__(self, root: Path, count: int) -> None:
        self.paths = [root / f"bucket-{i:03d}.bin" for i in range(count)]
        self.handles = [path.open("wb") for path in self.paths]
        self.buffers = [bytearray() for _ in self.paths]

    def append(self, bucket: int, term: int, doc: int) -> None:
        buffer = self.buffers[bucket]
        buffer.extend(RECORD.pack(term, doc))
        if len(buffer) >= BUFFER_LIMIT:
            self.handles[bucket].write(buffer)
            buffer.clear()

    def close(self) -> None:
        for handle, buffer in zip(self.handles, self.buffers, strict=True):
            if buffer:
                handle.write(buffer)
            handle.close()


def build(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    stats_path = resolve_stats_path(args.corpus, args.stats)
    stats_root, term_rows = load_term_statistics(stats_path)
    old_id_by_term = {row["term_id"]: old_id for old_id, row in enumerate(term_rows)}
    keep_old_ids = [
        old_id
        for old_id, row in enumerate(term_rows)
        if args.max_df <= 0 or row["df"] <= args.max_df
    ]
    if not keep_old_ids:
        raise ValueError("pruning removed every term")
    old_to_new = {old_id: new_id for new_id, old_id in enumerate(keep_old_ids)}

    if args.index_dir.exists():
        shutil.rmtree(args.index_dir)
    args.index_dir.mkdir(parents=True)
    spool = args.index_dir / ".spool"
    spool.mkdir()
    buckets = BucketWriter(spool, args.bucket_count)
    doc_count = 0
    input_postings = 0
    kept_postings = 0
    docs_path = args.index_dir / "docs.txt"
    try:
        with docs_path.open("w", encoding="utf-8") as docs:
            for doc_no, row in enumerate(load_rows(args.corpus)):
                doc_id = str(row.get("doc_id", row.get("_id", "")))
                if not doc_id or "\n" in doc_id:
                    raise ValueError(f"invalid document ID at row {doc_no + 1}")
                docs.write(doc_id + "\n")
                for term in parse_terms(row):
                    input_postings += 1
                    old_id = old_id_by_term.get(term)
                    if old_id is None:
                        raise ValueError(f"term {term!r} missing from statistics")
                    new_id = old_to_new.get(old_id)
                    if new_id is not None:
                        buckets.append(new_id % args.bucket_count, new_id, doc_no)
                        kept_postings += 1
                doc_count = doc_no + 1
    finally:
        buckets.close()

    expected_docs = int(stats_root.get("document_count", doc_count))
    if doc_count != expected_docs:
        raise ValueError(f"corpus row count mismatch: {doc_count} != {expected_docs}")

    term_meta = np.zeros(len(keep_old_ids), dtype=TERM_META_DTYPE)
    term_meta["old_id"] = np.asarray(keep_old_ids, dtype="<u4")
    current_posting = 0
    current_block = 0
    docs_out_path = args.index_dir / "postings.docs.bin"
    blocks_path = args.index_dir / "block_lengths.bin"
    with docs_out_path.open("wb") as docs_out, blocks_path.open("wb") as blocks_out:
        for bucket_path in buckets.paths:
            records = np.fromfile(bucket_path, dtype=RECORD_DTYPE)
            if records.size == 0:
                continue
            order = np.argsort(records["term"], kind="stable")
            records = records[order]
            terms = records["term"]
            starts = np.r_[0, np.flatnonzero(terms[1:] != terms[:-1]) + 1]
            ends = np.r_[starts[1:], records.size]
            for start, end in zip(starts.tolist(), ends.tolist(), strict=True):
                term_id = int(terms[start])
                doc_values = records["doc"][start:end].astype("<u4", copy=False)
                doc_values.tofile(docs_out)
                length = end - start
                block_count = (length + args.block_size - 1) // args.block_size
                for block in range(block_count):
                    block_len = min(args.block_size, length - block * args.block_size)
                    blocks_out.write(struct.pack("<I", block_len))
                term_meta[term_id]["offset"] = current_posting
                term_meta[term_id]["length"] = length
                term_meta[term_id]["block_offset"] = current_block
                term_meta[term_id]["block_count"] = block_count
                term_meta[term_id]["df"] = length
                term_meta[term_id]["idf"] = math.log1p(doc_count / max(length, 1))
                current_posting += length
                current_block += block_count
    if current_posting != kept_postings:
        raise ValueError(f"posting write mismatch: {current_posting} != {kept_postings}")
    shutil.rmtree(spool)

    # Physical metadata rows use compacted IDs after max-DF pruning, so query
    # terms must map to those compacted rows rather than their source row IDs.
    dictionary = {
        term_rows[old_id]["term_id"]: new_id
        for new_id, old_id in enumerate(keep_old_ids)
    }
    (args.index_dir / "dictionary.json").write_text(
        json.dumps(dictionary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    np.save(args.index_dir / "term_meta.npy", term_meta, allow_pickle=False)
    manifest = {
        "format_version": FORMAT_VERSION,
        "document_count": doc_count,
        "source_term_count": len(term_rows),
        "indexed_term_count": len(keep_old_ids),
        "input_postings": input_postings,
        "indexed_postings": kept_postings,
        "block_size": args.block_size,
        "corpus_sha256": sha256_file(args.corpus),
        "stats_sha256": sha256_file(stats_path),
        "build_seconds": time.perf_counter() - started,
        "blind": True,
        "known_defects": [],
    }
    (args.index_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def search(args: argparse.Namespace) -> None:
    manifest = json.loads((args.index_dir / "manifest.json").read_text())
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported index format")
    doc_ids = (args.index_dir / "docs.txt").read_text().splitlines()
    dictionary = json.loads((args.index_dir / "dictionary.json").read_text())
    term_meta = np.load(args.index_dir / "term_meta.npy", mmap_mode="r", allow_pickle=False)
    postings = np.memmap(args.index_dir / "postings.docs.bin", dtype="<u4", mode="r")
    if len(doc_ids) != int(manifest["document_count"]):
        raise ValueError("document table does not match manifest")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    latencies: list[float] = []
    totals = {"posting_evaluations": 0, "scored_candidates": 0}
    scores = np.zeros(len(doc_ids), dtype=np.float64)
    started = time.perf_counter()
    with args.output.open("w", encoding="utf-8") as output:
        for row in load_rows(args.queries):
            query_started = time.perf_counter()
            query_id = str(row.get("query_id", row.get("_id", "")))
            if not query_id:
                raise ValueError("query is missing query_id/_id")
            scores.fill(0.0)
            for term in parse_terms(row):
                physical = dictionary.get(term)
                if not isinstance(physical, int) or not 0 <= physical < len(term_meta):
                    continue
                meta = term_meta[physical]
                start = int(meta["offset"])
                end = start + int(meta["length"])
                contribution = float(meta["idf"])
                scores[postings[start:end]] += contribution
                totals["posting_evaluations"] += end - start
            candidates = np.flatnonzero(scores > 0.0)
            totals["scored_candidates"] += int(candidates.size)
            if candidates.size > args.top_k:
                values = scores[candidates]
                selected = np.argpartition(values, -args.top_k)[-args.top_k:]
                cutoff = float(values[selected].min())
                candidates = candidates[values >= cutoff]
            ranked = sorted(
                candidates.tolist(),
                key=lambda doc: (-float(scores[doc]), doc_ids[doc]),
            )[: args.top_k]
            output.write(
                json.dumps(
                    {
                        "query_id": query_id,
                        "results": [
                            {"doc_id": doc_ids[doc], "score": float(scores[doc])}
                            for doc in ranked
                        ],
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            latencies.append((time.perf_counter() - query_started) * 1000.0)
    values = np.asarray(latencies, dtype=np.float64)
    metrics = {
        "query_count": len(latencies),
        "wall_seconds": time.perf_counter() - started,
        "latency_ms": {
            "mean": float(values.mean()) if values.size else 0.0,
            "p50": float(np.percentile(values, 50)) if values.size else 0.0,
            "p95": float(np.percentile(values, 95)) if values.size else 0.0,
            "p99": float(np.percentile(values, 99)) if values.size else 0.0,
        },
        **totals,
    }
    Path(str(args.output) + ".metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--corpus", type=Path, required=True)
    build_parser.add_argument("--index-dir", type=Path, required=True)
    build_parser.add_argument("--cache-dir", type=Path)
    build_parser.add_argument("--stats", type=Path)
    build_parser.add_argument("--max-df", type=int, default=DEFAULT_MAX_DF)
    build_parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
    build_parser.add_argument("--bucket-count", type=int, default=DEFAULT_BUCKET_COUNT)
    search_parser = sub.add_parser("search")
    search_parser.add_argument("--index-dir", type=Path, required=True)
    search_parser.add_argument("--queries", type=Path, required=True)
    search_parser.add_argument("--output", type=Path, required=True)
    search_parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()
    if getattr(args, "block_size", 1) <= 0 or getattr(args, "bucket_count", 1) <= 0:
        parser.error("block and bucket counts must be positive")
    if getattr(args, "top_k", 1) <= 0:
        parser.error("top-k must be positive")
    return args


def main() -> None:
    args = parse_args()
    (build if args.command == "build" else search)(args)


if __name__ == "__main__":
    main()
