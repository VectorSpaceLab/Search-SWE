"""Socket-only isolation probes. Test payloads never contain real credentials."""

import json
import socket
import socketserver
import sys
import threading

import lifecyclefixture
import s0fixture


class Receiver(socketserver.BaseRequestHandler):
    def handle(self):
        if isinstance(self.request, tuple):
            packet, sock = self.request
        else:
            sock = self.request
            sock.settimeout(3)
            packet = sock.recv(100)
        if packet:
            print(json.dumps({"kind": self.server.kind}), flush=True)
            if not isinstance(self.request, tuple):
                sock.sendall(b"OK")


class V6(s0fixture.Server):
    address_family = socket.AF_INET6


def serve(target, direct=False):
    if target:
        servers = [(s0fixture.Server(("0.0.0.0", 18083), Receiver), "cross_inbound")]
    else:
        servers = [(s0fixture.Server(("0.0.0.0", 18080), lifecyclefixture.Proxy), "proxy"),
                   (socketserver.ThreadingUDPServer(("0.0.0.0", 18081), Receiver), "udp"),
                   (V6(("::", 18082), Receiver), "ipv6")]
        if direct:
            servers.extend([(s0fixture.Server(("0.0.0.0", 443), lifecyclefixture.DirectHTTP), "http"),
                            (socketserver.ThreadingUDPServer(("0.0.0.0", 53), lifecyclefixture.DirectDNS), "dns")])
    for server, kind in servers:
        server.kind = kind
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({"kind": "ready"}), flush=True)
    threading.Event().wait()


def probe(mode, address):
    if mode == "capabilities":
        for family, kind, protocol in [(socket.AF_PACKET, socket.SOCK_RAW, 0),
                                       (socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)]:
            try:
                sock = socket.socket(family, kind, protocol)
            except PermissionError:
                continue
            sock.close()
            raise AssertionError("raw socket permitted")
        print("raw sockets denied")
        return
    if mode == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"fixture", (address, 18081))
        return
    ports = {"ipv6": 18082, "cross": 18083, "proxy-allow": 18080, "proxy-deny": 18080, "metadata": 443, "api": 443}
    with socket.create_connection((address, ports[mode]), timeout=3) as sock:
        if mode.startswith("proxy-"):
            host = "allowed.example" if mode.endswith("allow") else "blocked.example"
            packet = f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode()
        elif mode == "metadata":
            packet = b"GET / HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n"
        elif mode == "api":
            packet = b"GET / HTTP/1.1\r\nHost: allowed.example\r\nConnection: close\r\n\r\n"
        else:
            packet = b"fixture"
        sock.sendall(packet)
        print("received bytes:", len(sock.recv(100)))


if __name__ == "__main__":
    if sys.argv[1] == "idle":
        print(json.dumps({"kind": "ready"}), flush=True)
        threading.Event().wait()
    elif sys.argv[1] in {"serve", "serve-direct", "target"}:
        serve(sys.argv[1] == "target", direct=sys.argv[1] == "serve-direct")
    else:
        try:
            probe(sys.argv[1], sys.argv[2])
        except OSError as error:
            print(type(error).__name__)
