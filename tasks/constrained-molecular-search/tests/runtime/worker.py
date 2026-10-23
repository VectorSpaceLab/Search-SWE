"""One persistent isolated submission; stdout carries only protocol frames."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys

from isolation import isolate

PROTOCOL = None

def emit(message):
    PROTOCOL.write(json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n")
    PROTOCOL.flush()


def main():
    global PROTOCOL
    PROTOCOL = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    # Redirect fd 1 as well as Python's stdout: native libraries and subprocesses
    # must not place ordinary logs in the JSON response channel.
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    work = Path(os.environ["MOLECULE_WORK_DIR"])
    library_dir = os.environ.get("MOLECULE_LIBRARY_DIR", "/task/library")
    isolate(work)
    first = json.loads(sys.stdin.readline())
    with contextlib.redirect_stdout(sys.stderr):
        sys.path.insert(0, "/app/submission")
        spec = importlib.util.spec_from_file_location("retriever", "/app/submission/retriever.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        index_dir = str(work / "index")
        Path(index_dir).mkdir(exist_ok=True)
        if first["op"] == "prepare":
            module.prepare(library_dir, "/task/models", index_dir)
        searcher = module.Searcher(library_dir, "/task/models", index_dir)
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    emit({"ready": True})
    for line in sys.stdin:
        request = json.loads(line)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                ids = searcher.search(request)
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
            emit({"query_id": request["query_id"], "ids": ids})
        except Exception as error:
            emit({"query_id": request["query_id"], "error": type(error).__name__})


if __name__ == "__main__":
    main()
