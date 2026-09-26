"""Offline receiving oracle and bounded continuous HTTP clients. No target dialing."""

import http.client
import json
from pathlib import Path
import socket
import socketserver
import struct
import threading
import time


class Receiver(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # The positive-control burst has eight simultaneous clients. The default
    # backlog of five can force a one-second SYN retry before the mock accepts.
    request_queue_size = 64

    def __init__(self, address, output, *, direct=False):
        self.events = []
        self.lock = threading.Lock()
        self.output = output
        self.direct = direct
        super().__init__(address, Handler)

    def record(self, **event):
        with self.lock:
            event["received_ns"] = time.monotonic_ns()
            self.events.append(event)
            with self.output.open("a") as stream:
                stream.write(json.dumps(event) + "\n")

    def snapshot(self):
        with self.lock:
            return list(self.events)


class DirectReceiver(Receiver):
    """Real direct HTTP + UDP DNS, bound only to ephemeral Docker-bridge ports."""

    def __init__(self, address, output):
        super().__init__(address, output, direct=True)
        try:
            self.dns = socketserver.ThreadingUDPServer((address[0], 0), DirectDNS)
        except BaseException:
            self.server_close()
            raise
        self.dns.origin = self
        threading.Thread(target=self.dns.serve_forever, daemon=True).start()

    def shutdown(self):
        self.dns.shutdown()
        super().shutdown()

    def server_close(self):
        if hasattr(self, "dns"):
            self.dns.server_close()
        super().server_close()

    def configuration(self, image):
        host, port = self.dns.server_address
        return {"version": 1, "mode": "direct", "image": image, "dns": {"servers": [f"{host}:{port}"]}}


class DirectDNS(socketserver.BaseRequestHandler):
    def handle(self):
        packet, sock = self.request
        offset, labels = 12, []
        while packet[offset]:
            size = packet[offset]
            if size > 63:
                raise ValueError("fixture expects an uncompressed DNS query")
            labels.append(packet[offset+1:offset+1+size].decode())
            offset += size + 1
        question = packet[12:offset+5]
        qtype, qclass = struct.unpack("!HH", packet[offset+1:offset+5])
        self.server.origin.record(kind="dns", host=".".join(labels), source=self.client_address[0])
        valid = qtype == 1 and qclass == 1
        response = packet[:2] + struct.pack("!5H", 0x8180, 1, int(valid), 0, 0) + question
        if valid:
            response += b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4)
            response += socket.inet_aton(self.server.origin.server_address[0])
        sock.sendto(response, self.client_address)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            line = self.rfile.readline(4096).decode().strip()
            if not line:
                return
            method, target, version = line.split()
            if self.server.direct:
                request = line
            else:
                if method != "CONNECT" or version != "HTTP/1.1":
                    raise ValueError("unexpected proxy request")
                self.headers()
                self.server.record(kind="connect", target=target, source=self.client_address[0])
                self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                self.wfile.flush()
                request = self.rfile.readline(4096).decode().strip()
            if not request:
                return
            method, path, version = request.split()
            headers = self.headers()
            if (method != "GET" or version != "HTTP/1.1"
                    or (not self.server.direct and target != headers.get("host", "") + ":80")):
                raise ValueError("origin/CONNECT mismatch in fixture")
            _, actor, phase, sent = path.split("/")
            self.server.record(kind="http", host=headers["host"].split(":")[0], actor=actor, phase=phase,
                               sent_ns=int(sent), source=self.client_address[0])
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
            self.wfile.flush()
        except (OSError, http.client.HTTPException):
            pass  # Client cancellation during revocation is expected.
        except Exception as error:
            self.server.record(kind="fixture_error", error=type(error).__name__)

    def headers(self):
        headers = {}
        for _ in range(32):
            line = self.rfile.readline(4096)
            if line in {b"\r\n", b"\n"}:
                return headers
            key, value = line.decode().split(":", 1)
            headers[key.lower()] = value.strip()
        raise ValueError("unbounded fixture headers")


def request(host, actor, phase, timeout=.25):
    row = {"host": host, "actor": actor, "phase": phase, "begin_ns": time.monotonic_ns(), "ok": False}
    try:
        # TEST-NET, not a real public API. The production transparent redirect
        # must route the named Host through the mock CONNECT upstream.
        port_file = Path("/tmp/searchswe-fixture-port")
        port = int(port_file.read_text()) if port_file.exists() else 80
        authority = host if port == 80 else f"{host}:{port}"
        with socket.create_connection(("198.51.100.42", port), timeout=timeout) as sock:
            row["sent_ns"] = time.monotonic_ns()
            packet = f"GET /{actor}/{phase}/{row['sent_ns']} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n"
            sock.sendall(packet.encode())
            response = http.client.HTTPResponse(sock)
            response.begin()
            row["ok"] = response.status == 200 and response.read() == b"OK"
    except (OSError, http.client.HTTPException) as error:
        row["error_class"] = type(error).__name__
    row["end_ns"] = time.monotonic_ns()
    return row
