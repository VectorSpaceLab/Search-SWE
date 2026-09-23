"""Jina retrieval transport over an inherited file descriptor."""
import json
import io
import os
import threading

_lock = threading.Lock()
_channel = None


def request(operation, **body):
    """Call embeddings or rerank with the provider JSON fields."""
    global _channel
    payload = {"operation": operation, "body": body}
    encoded = json.dumps(payload).encode() + b"\n"
    if len(encoded) > 131072:
        raise ValueError("Jina request exceeds 128 KiB")
    with _lock:
        if _channel is None:
            fd = int(os.environ["TASK_JINA_FD"])
            _channel = io.BufferedRWPair(os.fdopen(os.dup(fd), "rb", buffering=0), os.fdopen(os.dup(fd), "wb", buffering=0))
        _channel.write(encoded)
        _channel.flush()
        result = json.loads(_channel.readline())
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["response"]


def embeddings(**body):
    return request("embeddings", **body)


def rerank(**body):
    return request("rerank", **body)
