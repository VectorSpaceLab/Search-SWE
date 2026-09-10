"""Stream the corpus into a lexical index, then start the shared search service."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid


def build(corpus, index_dir, text_chars):
    index_dir.mkdir(parents=True, exist_ok=True)
    database = index_dir / "corpus.sqlite"
    manifest_path = index_dir / "index.json"
    source = corpus.stat()
    fingerprint = {"format": 1, "corpus_bytes": source.st_size,
                   "corpus_mtime_ns": source.st_mtime_ns, "text_chars": text_chars}
    try:
        reusable = database.is_file() and json.loads(manifest_path.read_text())["source"] == fingerprint
    except (OSError, ValueError, KeyError):
        reusable = False
    if not reusable:
        temporary = index_dir / "building.sqlite"
        temporary.unlink(missing_ok=True)
        count = 0
        with sqlite3.connect(temporary) as db:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA cache_size=-65536")
            db.execute("CREATE VIRTUAL TABLE docs USING fts5(docid UNINDEXED, text, url UNINDEXED, tokenize='porter unicode61')")
            batch = []
            with corpus.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    batch.append((str(row["docid"]), row["text"][:text_chars], row.get("url", "")))
                    count += 1
                    if len(batch) == 1000:
                        db.executemany("INSERT INTO docs VALUES (?, ?, ?)", batch)
                        db.commit()
                        batch.clear()
                db.executemany("INSERT INTO docs VALUES (?, ?, ?)", batch)
                db.commit()
            if count < 5:
                raise ValueError("corpus must contain at least five documents")
        temporary.replace(database)
        manifest_path.write_text(json.dumps({"source": fingerprint, "document_count": count}, indent=2) + "\n")
        print(f"Indexed {count} documents", flush=True)
    runtime = index_dir / "service.json"
    # A build call may be repeated during development while the service is alive.
    try:
        previous = json.loads(runtime.read_text())
        with urllib.request.urlopen(previous["url"] + "/health", timeout=2) as response:
            health = json.load(response)
        if health == {"database": str(database), "token": previous["token"]}:
            return
    except (OSError, ValueError, KeyError):
        pass
    runtime.unlink(missing_ok=True)
    token = uuid.uuid4().hex
    with (index_dir / "service.log").open("a") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("search_service.py")),
             "--database", str(database), "--runtime", str(runtime), "--token", token],
            stdout=log, stderr=log, start_new_session=True,
        )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("search service failed; inspect index-dir/service.log")
        try:
            settings = json.loads(runtime.read_text())
            with urllib.request.urlopen(settings["url"] + "/health", timeout=1) as response:
                if json.load(response)["token"] == token:
                    return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("search service did not become ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--text-chars", type=int, default=6000)
    args = parser.parse_args()
    if args.text_chars <= 0:
        parser.error("--text-chars must be positive")
    build(args.corpus.resolve(), args.index_dir.resolve(), args.text_chars)
