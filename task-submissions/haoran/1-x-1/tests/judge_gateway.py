"""Credential-holding relay for the trajectory judge's Responses API calls."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests


class JudgeGateway:
    def __init__(self, base_url, key, model):
        if not base_url or not key or not model:
            raise ValueError("Trajectory judge API configuration is required")
        self.base_url, self.key, self.model = base_url.rstrip("/"), key, model
        self.token = secrets.token_urlsafe(32)
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + gateway.token:
                    self.send_error(403)
                    return
                if self.path not in ("/responses", "/responses/compact"):
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16 * 1024 * 1024:
                        raise ValueError("invalid request size")
                    payload = json.loads(self.rfile.read(length))
                    if payload.get("model") != gateway.model:
                        raise ValueError("unconfigured model")
                except (ValueError, TypeError, AttributeError):
                    self.send_error(400)
                    return
                try:
                    # Only the parent holds the provider credential.
                    with requests.post(
                        gateway.base_url + self.path,
                        headers={"Authorization": "Bearer " + gateway.key},
                        json=payload, stream=True, timeout=(10, 180), allow_redirects=False,
                    ) as upstream:
                        if upstream.status_code != 200:
                            self.send_error(502, "Judge model service failed")
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        for block in upstream.iter_content(chunk_size=4096):
                            if block:
                                self.wfile.write(block)
                                self.wfile.flush()
                except (requests.RequestException, OSError):
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
