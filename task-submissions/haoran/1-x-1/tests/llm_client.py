"""Chat API transport handed to the answerer over an inherited file descriptor."""
import json
import io
import os
import threading

_lock = threading.Lock()
_channel = None


def chat_completion(messages, **options):
    """Send one Chat Completions request to the configured endpoint and model."""
    global _channel
    payload = dict(options, messages=messages)
    encoded = json.dumps(payload).encode() + b"\n"
    if len(encoded) > 131072:
        raise ValueError("generation request exceeds 128 KiB")
    with _lock:
        if _channel is None:
            fd = int(os.environ["TASK_LLM_FD"])
            _channel = io.BufferedRWPair(os.fdopen(os.dup(fd), "rb", buffering=0), os.fdopen(os.dup(fd), "wb", buffering=0))
        _channel.write(encoded)
        _channel.flush()
        result = json.loads(_channel.readline())
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["response"]
