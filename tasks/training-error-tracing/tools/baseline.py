"""Reproducible text, fixed training-feature and compact-probe retrieval baselines.

The service caches fixed training features and model state. A gradient used for
an error query is freshly computed for that request; error-query gradients and
rankings are never stored for future requests.
"""

import argparse
import hashlib
import json
import os
import socket
import socketserver
import subprocess
import sys
import time
from pathlib import Path

MODES = ["efficient-source", "target", "frequency", "prompt-absent", "bm25", "bm25-target",
         "base-nll-mean", "base-nll-max", "entity-ranker", "source-mode", "source-frequency", "query-source-text"]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()



def request(index, query, action="query"):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(9.8)
        client.connect(str(index / "retriever.sock"))
        client.sendall((json.dumps({"action": action, "query": query})+"\n").encode())
        with client.makefile("rb") as stream:
            raw = stream.readline(1024*1024)
    result = json.loads(raw)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def serve(args):
    if args.mode == "efficient-source":
        from lexical_source import MatureSource as Retriever
    else:
        from retrieval_index import Retriever
    retriever = Retriever(args)
    socket_path = args.index_dir / "retriever.sock"
    socket_path.unlink(missing_ok=True)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                payload = json.loads(self.rfile.readline(1024*1024))
                result = retriever.rank(payload["query"], payload.get("action", "query"))
            except Exception as error:
                result = {"error": type(error).__name__ + ": " + str(error)}
            self.wfile.write((json.dumps(result, allow_nan=False)+"\n").encode())

    with socketserver.UnixStreamServer(str(socket_path), Handler) as server:
        (args.index_dir / "service.ready.json").write_text(json.dumps({"pid": os.getpid(), "mode": args.mode})+"\n")
        server.serve_forever(poll_interval=.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "serve", "query", "features"])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, default="frequency")
    parser.add_argument("--base-nll", type=Path)
    parser.add_argument("--base-alternatives", type=Path)
    parser.add_argument("--ranker", type=Path)
    parser.add_argument("--query", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    if args.top_k != 10:
        raise ValueError("This baseline implements Top-10")
    if args.action in {"query", "features"}:
        result = request(args.index_dir, json.loads(args.query.read_text()), args.action)
        args.output.write_text(json.dumps(result, allow_nan=False)+"\n")
    elif args.action == "serve":
        serve(args)
    else:
        args.index_dir.mkdir(parents=True, exist_ok=True)
        ready = args.index_dir / "service.ready.json"
        if ready.exists():
            raise ValueError("Use a fresh index directory or stop the previous service")
        command = [sys.executable, str(Path(__file__).resolve()), "serve",
                   "--data-dir", str(args.data_dir.resolve()), "--model-dir", str(args.model_dir.resolve()),
                   "--index-dir", str(args.index_dir.resolve()), "--mode", args.mode]
        for flag, value in [("--base-nll", args.base_nll), ("--base-alternatives", args.base_alternatives), ("--ranker", args.ranker)]:
            if value:
                command.extend([flag, str(value.resolve())])
        with (args.index_dir / "service.log").open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic()+1700
        while not ready.exists():
            if process.poll() is not None:
                raise RuntimeError("Service initialization failed; inspect index-dir/service.log")
            if time.monotonic() > deadline:
                process.terminate()
                raise TimeoutError("Service initialization exceeded the preparation budget")
            time.sleep(.05)


if __name__ == "__main__":
    main()
