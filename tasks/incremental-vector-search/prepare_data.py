#!/usr/bin/env python3
"""Offline, deterministic conversion of pinned upstream inputs; never run by a solver."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
SEED = 260306660
SOURCE_SAMPLE_SEED = 260306661
COUNT, INITIAL, BATCH, STAGES = 125_000, 105_000, 1000, 10
MAX_DOWNLOAD_BYTES = 5_000_000_000


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def split_rows(count=COUNT, initial=INITIAL, batch=BATCH, stages=STAGES):
    if count != initial + 2 * batch * stages:
        raise ValueError("Split sizes do not cover exactly the source rows")
    order = np.random.Generator(np.random.PCG64(SEED)).permutation(count)
    return order[:initial], order[initial:initial + batch * stages], order[initial + batch * stages:]


def source_order(source_count, count=COUNT):
    """Choose source rows without replacement, then partition independent roles."""
    if source_count < count:
        raise ValueError("Pinned shards contain too few source rows")
    return np.random.Generator(np.random.PCG64(SOURCE_SAMPLE_SEED)).choice(
        source_count, count, replace=False)


def set_public_permissions(directory):
    """Read-only bind mounts must also be readable by the verifier's submission UID."""
    directory.chmod(0o755)
    for path in directory.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


def prepare(dim):
    manifest_entries = json.loads((ROOT / "assets.json").read_text())["files"]
    if sum(e["size_bytes"] for e in manifest_entries) >= MAX_DOWNLOAD_BYTES:
        raise ValueError("Downloadable task assets must remain below decimal 5 GB")
    entries = [e for e in manifest_entries
               if e["path"].startswith(f"data/upstream/{dim}/")]
    if not entries:
        raise ValueError("Missing pinned source files")
    source_count = 0
    for entry in entries:
        path = ROOT / entry["path"]
        if path.stat().st_size != entry["size_bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"Source checksum failed: {path}")
        source_count += pq.ParquetFile(path).metadata.num_rows
    selected = source_order(source_count, COUNT)
    public = ROOT / f"data/public/{dim}"
    private = ROOT / f"data/private/{dim}"
    public.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    initial_rows, insert_rows, query_rows = split_rows(COUNT, INITIAL, BATCH, STAGES)
    # Build a source-row -> destination-row lookup without materializing all vectors.
    order = selected[np.concatenate([initial_rows, insert_rows, query_rows])]
    destination = np.full(source_count, -1, dtype=np.int64)
    destination[order] = np.arange(COUNT)
    arrays = [np.lib.format.open_memmap(path, mode="w+", dtype="<f4", shape=(count, dim))
              for path, count in [(public / "initial.npy", INITIAL),
                                  (private / "inserts.npy", BATCH * STAGES),
                                  (private / "queries.npy", BATCH * STAGES)]]
    column = f"text-embedding-3-large-{dim}-embedding"
    offset = 0
    for entry in entries:
        path = ROOT / entry["path"]
        for batch in pq.ParquetFile(path).iter_batches(batch_size=2048, columns=[column]):
            values = batch.column(0)
            if values.null_count or values.flatten().null_count:
                raise ValueError(f"Null source vectors: {path}")
            if not np.all(np.diff(values.offsets.to_numpy()) == dim):
                raise ValueError(f"Inconsistent source dimensions: {path}")
            vectors = np.asarray(values.flatten().to_numpy(zero_copy_only=False), dtype="<f4").reshape(-1, dim)
            if vectors.shape != (len(batch), dim) or not np.isfinite(vectors).all():
                raise ValueError(f"Invalid source vectors: {path}")
            end = offset + len(vectors)
            if end > source_count:
                raise ValueError("Source row count changed during preparation")
            dest = destination[offset:end]
            for array, lo, hi in zip(arrays, [0, INITIAL, INITIAL + BATCH * STAGES],
                                     [INITIAL, INITIAL + BATCH * STAGES, COUNT]):
                mask = (dest >= lo) & (dest < hi)
                array[dest[mask] - lo] = vectors[mask]
            offset = end
        print(f"{dim}: {offset}/{source_count} pinned source vectors", flush=True)
    if offset != source_count:
        raise ValueError(f"Expected {source_count} source rows, found {offset}")
    for array in arrays:
        array.flush()
    # Development is an independent small workload taken only from the initial rows.
    # Its queries are excluded from its own corpus and never overlap hidden queries.
    development = public / "development"
    development.mkdir(exist_ok=True)
    np.save(development / "initial.npy", arrays[0][:10_000])
    np.save(development / "inserts.npy", arrays[0][10_000:11_000])
    np.save(development / "queries.npy", arrays[0][11_000:12_000])
    # Warmup only uses already-public initial vectors; not held-out search vectors.
    np.save(public / "warmup.npy", arrays[0][12_000:12_008])
    np.save(private / "source_rows.npy", order)
    paths = [public / "initial.npy", public / "warmup.npy", *development.glob("*.npy"),
             private / "inserts.npy", private / "queries.npy", private / "source_rows.npy"]
    manifest = {"schema_version": 1, "seed": SEED, "dimension": dim,
                "initial": INITIAL, "batch": BATCH, "stages": STAGES,
                "selected_count": COUNT, "available_source_rows": source_count,
                "source_sample_seed": SOURCE_SAMPLE_SEED,
                "source_selection": "PCG64 without replacement over concatenated pinned shards",
                "source_shards": [e["path"] for e in entries],
                "precision": "little-endian float32, no normalization",
                "files": [{"path": str(p.relative_to(ROOT)), "size_bytes": p.stat().st_size,
                           "sha256": digest(p)} for p in sorted(paths)]}
    (private / "derived-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (public / "config.json").write_text(json.dumps({k: manifest[k] for k in
        ["dimension", "initial", "batch", "stages", "precision"]}, indent=2) + "\n")
    set_public_permissions(public.parent)
    print(f"{dim}: preparation complete; exact answers and calibration are separate steps", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimension", type=int, choices=[1536, 3072], nargs="+", default=[1536, 3072])
    args = parser.parse_args()
    for dimension in args.dimension:
        prepare(dimension)
