"""Proxy that holds the API credential and forwards answerer requests upstream."""
import json
import socket
import threading
from pathlib import Path
import requests


class Gateway:
    class Error(RuntimeError):
        """The generation service failed, which is an infrastructure error."""

    def __init__(self, key, limit, log, base_url, model):
        if not key or not base_url or not model:
            raise self.Error("Answer API key, base URL and model are required")
        self.key, self.limit, self.log = key, limit, Path(log)
        self.base_url, self.model = base_url.rstrip("/"), model
        self.parent, self.worker = socket.socketpair()
        self.calls = 0
        self.failures = []
        self.upstream_error = False
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.worker.close()
        try:
            self.parent.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.parent.close()
        self.thread.join(timeout=1)
        self.log.write_text(json.dumps({"calls": self.calls, "errors": self.failures}) + "\n")
        if self.upstream_error:
            raise self.Error("Generation service failed; see generation-api.json")

    @staticmethod
    def validate(payload, model):
        allowed = {"model", "messages", "temperature", "top_p", "max_tokens", "response_format", "thinking"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("unsupported generation request fields")
        if payload.get("model", model) != model:
            raise ValueError("only the configured answer model is allowed")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
            raise ValueError("messages must contain 1..32 messages")
        if any(not isinstance(m, dict) or set(m) != {"role", "content"} or m["role"] not in ("system", "user", "assistant") or not isinstance(m["content"], str) for m in messages):
            raise ValueError("invalid messages")
        tokens = payload.get("max_tokens", 1000)
        if type(tokens) is not int or not 1 <= tokens <= 2000:
            raise ValueError("max_tokens must be 1..2000")
        return dict(payload, model=model, max_tokens=tokens)

    def forward(self, payload):
        try:
            response = requests.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + self.key},
                json=payload, timeout=(10, 45), allow_redirects=False,
            )
            if response.status_code in (400, 413, 422):
                raise ValueError(f"Invalid generation request: HTTP {response.status_code}")
            if response.status_code != 200:
                raise self.Error(f"Generation upstream HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise self.Error("Generation upstream invalid JSON") from None
        except self.Error:
            raise
        except requests.RequestException:
            raise self.Error("Generation upstream transport or JSON failure") from None

    def serve(self):
        try:
            with self.parent.makefile("rwb") as channel:
                while True:
                    line = channel.readline(131073)
                    if not line:
                        break
                    try:
                        if len(line) > 131072 or not line.endswith(b"\n"):
                            raise ValueError("generation request exceeds 128 KiB")
                        payload = self.validate(json.loads(line), self.model)
                        self.calls += 1
                        if self.calls > self.limit:
                            raise ValueError("generation call budget exceeded")
                        result = {"response": self.forward(payload)}
                    except self.Error as e:
                        self.upstream_error = True
                        self.failures.append(str(e))
                        result = {"error": str(e)}
                    except (ValueError, TypeError) as e:
                        self.failures.append(str(e))
                        result = {"error": str(e)}
                    channel.write(json.dumps(result).encode() + b"\n")
                    channel.flush()
                    if len(line) > 131072 or self.calls > self.limit:
                        break
        except (OSError, ValueError):
            pass
