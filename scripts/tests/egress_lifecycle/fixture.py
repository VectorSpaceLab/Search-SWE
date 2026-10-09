"""Offline upstream + held-connection fixture. Never dials requested targets."""

import http.client
import json
from pathlib import Path
import socket
import socketserver
import struct
import sys
import threading
import time

import s0fixture


class Proxy(socketserver.StreamRequestHandler):
    def handle(self):
        # Exceed the 30-second lease and the long-idle positive control. A
        # short fixture timeout would falsely "prove" old-socket revocation.
        self.connection.settimeout(120)
        try:
            request = self.rfile.readline(4096)
            if not request:
                return
            while self.rfile.readline(4096) not in (b"\r\n", b"\n", b""):
                pass
            print(json.dumps({"kind": "connect", "request": request.decode().strip()}), flush=True)
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.wfile.flush()
            if request == b"CONNECT resolver.example:15353 HTTP/1.1\r\n":
                s0fixture.MockDNS.handle(self)
                return
            while True:
                line = self.rfile.readline(4096)
                if not line:
                    return
                headers = {}
                while True:
                    header = self.rfile.readline(4096)
                    if header in (b"\r\n", b"\n", b""):
                        break
                    key, value = header.decode().split(":", 1)
                    headers[key.lower()] = value.strip()
                print(json.dumps({"kind": "http", "host": headers.get("host"),
                                  "request": line.decode().strip()}), flush=True)
                self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                self.wfile.flush()
                if headers.get("connection") == "close":
                    return
        except (TimeoutError, ConnectionError, EOFError):
            return


def serve():
    server = s0fixture.Server(("0.0.0.0", 18080), Proxy)
    print(json.dumps({"kind": "ready"}), flush=True)
    server.serve_forever()


class DirectHTTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(120)
        try:
            while True:
                line = self.rfile.readline(4096)
                if not line:
                    return
                headers = {}
                while True:
                    header = self.rfile.readline(4096)
                    if header in (b"\r\n", b"\n", b""):
                        break
                    key, value = header.decode().split(":", 1)
                    headers[key.lower()] = value.strip()
                print(json.dumps({"kind": "http", "host": headers.get("host"),
                                  "request": line.decode().strip()}), flush=True)
                self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                self.wfile.flush()
                if headers.get("connection") == "close":
                    return
        except (TimeoutError, ConnectionError, EOFError):
            return


class DirectDNS(socketserver.BaseRequestHandler):
    def handle(self):
        packet, sock = self.request
        questions = s0fixture.questions(packet)
        print(json.dumps({"kind": "dns", "questions": questions}), flush=True)
        address = socket.inet_aton(socket.gethostbyname(socket.gethostname()))
        # These test clients send a single uncompressed A question. Ignore any
        # EDNS tail and provide an actual address for the direct router.
        offset = 12
        while packet[offset]:
            offset += packet[offset] + 1
        question = packet[12:offset + 5]
        response = packet[:2] + struct.pack("!5H", 0x8180, 1, 1, 0, 0) + question
        response += b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4) + address
        sock.sendto(response, self.client_address)


def serve_direct():
    for port in (80, 443):
        server = s0fixture.Server(("0.0.0.0", port), DirectHTTP)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    dns = socketserver.ThreadingUDPServer(("0.0.0.0", 53), DirectDNS)
    threading.Thread(target=dns.serve_forever, daemon=True).start()
    print(json.dumps({"kind": "ready"}), flush=True)
    threading.Event().wait()


def dns_probe(case):
    host = "allowed.example" if case == "dns-allow" else "blocked.example"
    packet = s0fixture.dns_packet([(host, 3 if case == "dns-chaos" else 1)])
    addresses = [("127.0.0.1", 1053)]
    if case == "docker-dns-bypass":
        addresses = [("127.0.0.11", int(line.split()[1].split(":")[1], 16))
                     for line in Path("/proc/net/udp").read_text().splitlines()[1:]
                     if line.split()[1].startswith("0B00007F:")]
        if not addresses:
            raise RuntimeError("embedded Docker DNS positive target missing")
    answers = []
    for address in addresses:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                sock.sendto(packet, address)
                response = sock.recv(4096)
                answers.append(struct.unpack("!6H", response[:12])[3])
        except (TimeoutError, ConnectionError, PermissionError):
            answers.append(0)
    print(json.dumps({"answers": sum(answers), "targets": len(addresses)}), flush=True)


def wait(squat=False):
    sockets = []
    if squat:
        for kind, port in ((socket.SOCK_STREAM, 12345), (socket.SOCK_STREAM, 1053), (socket.SOCK_DGRAM, 1053)):
            sock = socket.socket(socket.AF_INET, kind)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            if kind == socket.SOCK_STREAM:
                sock.listen()
            sockets.append(sock)
    print(json.dumps({"kind": "ready"}), flush=True)
    threading.Event().wait()


def held(destination):
    with socket.create_connection((destination, 443), timeout=4) as sock:
        request = b"GET /held HTTP/1.1\r\nHost: allowed.example\r\n\r\n"
        sock.sendall(request)
        response = http.client.HTTPResponse(sock)
        response.begin()
        assert response.status == 200 and response.read() == b"OK"
        print(json.dumps({"kind": "ready"}), flush=True)
        deadline = time.monotonic() + 60
        while not Path("/tmp/release").exists():
            if time.monotonic() > deadline:
                raise TimeoutError("held fixture not released")
            time.sleep(.05)
        try:
            sock.sendall(request)
            print("post-transition response bytes:", len(sock.recv(1024)), flush=True)
        except (TimeoutError, ConnectionError) as error:
            print(type(error).__name__, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        serve()
    elif sys.argv[1] == "serve-direct":
        serve_direct()
    elif sys.argv[1] == "dns-probe":
        dns_probe(sys.argv[2])
    elif sys.argv[1] in {"idle", "squat"}:
        wait(sys.argv[1] == "squat")
    else:
        if sys.argv[1] == "wait-held":
            print(json.dumps({"kind": "started"}), flush=True)
            deadline = time.monotonic() + 60
            while not Path("/tmp/begin").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("fixture start timeout")
                time.sleep(.05)
        held(sys.argv[2])
