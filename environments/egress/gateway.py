#!/usr/bin/env python3
"""Trusted per-environment gateway controller; no proxy/DNS protocol parsing.

Only this container receives NET_ADMIN/NET_RAW and the private input mount.
Task containers share its network namespace, not its PID or mount namespace.
The control socket is filesystem-only and never mounted into task containers.
"""

import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time


RUN = Path("/run/searchswe")
READY = Path("/tmp/harbor-docker-egress-control-sidecar.ready")
CONTROL = RUN / "control.sock"
MARK = "114514"
LEASE_SECONDS = 30
DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def policy(mode, hosts, *, allow_public=False):
    modes = {"allowlist", "no-network", "public"} if allow_public else {"allowlist", "no-network"}
    if mode not in modes or not isinstance(hosts, list):
        raise ValueError("unsupported network policy")
    if any(not isinstance(h, str) or not DOMAIN.fullmatch(h) for h in hosts):
        raise ValueError("only lowercase exact DNS hosts are supported")
    if mode == "no-network" and hosts:
        raise ValueError("no-network must not contain hosts")
    return {"mode": mode, "hosts": sorted(set(hosts))}


def gost_config(settings, hosts):
    if settings.get("transport") == "direct":
        # Resolve the approved HTTP authority/SNI independently of the task's
        # original IP. Resolution goes through the same filtered DNS handler.
        services = [{"name": "approved-api", "addr": "127.0.0.1:12345", "bypass": "phase",
                     "resolver": "phase-dns", "metadata": {"so_mark": MARK},
                     "handler": {"type": "red", "metadata": {
                         "sniffing": True, "sniffing.timeout": "5s", "sniffing.fallback": False}},
                     "listener": {"type": "red"}}]
        for protocol in ("udp", "tcp"):
            services.append({"name": "approved-dns-" + protocol, "addr": "127.0.0.1:1053", "bypass": "phase",
                             "metadata": {"so_mark": MARK},
                             "handler": {"type": "dns", "metadata": {
                                 "dns": ",".join("udp://" + address + ("" if ":" in address else ":53")
                                                 for address in settings["dns_servers"]),
                                 "timeout": "10s", "readTimeout": "12s"}},
                             "listener": {"type": "dns", "metadata": {"mode": protocol}}})
        return {"log": {"level": "error"}, "services": services,
                "bypasses": [{"name": "phase", "whitelist": True, "matchers": hosts}],
                "resolvers": [{"name": "phase-dns", "nameservers": [
                    {"addr": "udp://127.0.0.1:1053", "only": "ipv4", "timeout": "12s"}]}]}
    node = {"name": "operator-upstream", "addr": settings["upstream_addr"],
            "metadata": {"so_mark": MARK}, "connector": {"type": "http"},
            "dialer": {"type": "tls" if settings["upstream_tls"] else "tcp"}}
    if settings.get("auth"):
        node["connector"]["auth"] = settings["auth"]
    if settings["upstream_tls"]:
        node["dialer"]["tls"] = {"serverName": settings["upstream_host"], "secure": True}
    # Do not enable recorders, sniffing fallback, raw TCP listeners or a
    # management API. All outbound sockets must travel via the sole chain.
    services = [{"name": "approved-api", "addr": "127.0.0.1:12345", "bypass": "phase",
                 "metadata": {"so_mark": MARK},
                 "handler": {"type": "red", "chain": "operator", "metadata": {
                     "sniffing": True, "sniffing.timeout": "5s", "sniffing.fallback": False}},
                 "listener": {"type": "red"}}]
    for protocol in ("udp", "tcp"):
        services.append({"name": "approved-dns-" + protocol, "addr": "127.0.0.1:1053", "bypass": "phase",
                         "metadata": {"so_mark": MARK},
                         "handler": {"type": "dns", "chain": "operator", "metadata": {
                             "dns": settings["doh_url"], "timeout": "10s", "readTimeout": "12s"}},
                         "listener": {"type": "dns", "metadata": {"mode": protocol}}})
    return {"log": {"level": "error"}, "services": services,
            "bypasses": [{"name": "phase", "whitelist": True, "matchers": hosts}],
            "chains": [{"name": "operator", "hops": [{"name": "transport", "nodes": [node]}]}]}


def nft(script):
    subprocess.run(["nft", "-f", "-"], input=script, text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5,
                   env={**os.environ, "TZ": "UTC"})


def close_gate():
    READY.unlink(missing_ok=True)
    # Separate, higher-priority filter: existing marked upstream sessions are
    # blocked too. Never flush/delete this gate as part of failure cleanup.
    nft("""add table inet searchswe_guard
flush table inet searchswe_guard
table inet searchswe_guard {
 chain output { type filter hook output priority -300; policy drop; oifname "lo" accept; }
 chain input { type filter hook input priority -300; policy drop; iifname "lo" accept; }
}
""")


def install_rules(settings, *, public=False):
    # upstream_ip and upstream_port are validated by the host adapter. Recheck
    # locally before interpolating nft syntax; no user-supplied shell code.
    import ipaddress
    direct = settings.get("transport") == "direct"
    if public and not direct:
        raise ValueError("public proxy egress is unsupported")
    if direct:
        # Only the trusted worker can set MARK. Test it before local acceptance
        # so even Docker's loopback DNS cannot escape the kernel lease.
        outgoing = f"meta mark {MARK} meta nfproto ipv4 jump lease\n  meta mark {MARK} drop"
    else:
        ip = str(ipaddress.IPv4Address(settings["upstream_ip"]))
        port = int(settings["upstream_port"])
        if not 1 <= port <= 65535:
            raise ValueError("invalid upstream port")
        outgoing = f"meta mark {MARK} ip daddr {ip} tcp dport {port} jump lease\n  meta mark {MARK} drop"
    redirect = f"""meta mark {MARK} return
  udp dport 53 redirect to :1053
  tcp dport 53 redirect to :1053
  fib daddr type local return
  meta l4proto tcp redirect to :12345"""
    if public:
        redirect = ""
        outgoing = "jump lease"
    nft(f"""add table inet searchswe_egress
flush table inet searchswe_egress
table inet searchswe_egress {{
 set leased_marks {{ type mark; flags timeout; timeout {LEASE_SECONDS}s; }}
 counter proxy_packets {{ }}
 chain lease {{ }}
 chain output {{ type nat hook output priority -110; policy accept;
  {redirect}
 }}
 chain egress {{ type filter hook output priority 0; policy drop;
  {outgoing}
  ip daddr 127.0.0.11 drop comment "embedded_dns_requires_worker"
  fib daddr type local counter accept comment "local_packets"
  counter drop comment "dropped_packets"
 }}
 chain input {{ type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related counter accept
  counter drop
 }}
}}
""")


def lease_remaining(deadline_ns):
    if type(deadline_ns) is not int:
        raise ValueError("invalid host lease")
    remaining = (deadline_ns - time.monotonic_ns()) // 1_000_000
    if not 0 < remaining <= LEASE_SECONDS * 1000:
        raise ValueError("expired or invalid host lease")
    return remaining


def packet_counters():
    """Packet counts, not HTTP requests or hostname authorization decisions."""
    try:
        output = subprocess.run(["nft", "-j", "list", "table", "inet", "searchswe_egress"],
                                capture_output=True, text=True, check=True, timeout=2).stdout
        counts = {}
        for item in json.loads(output)["nftables"]:
            counter = item.get("counter", {})
            if counter.get("name") == "proxy_packets":
                counts["proxy_packets"] = {key: counter[key] for key in ("packets", "bytes")}
            rule = item.get("rule", {})
            if rule.get("comment") in {"local_packets", "proxy_packets", "dropped_packets"}:
                for expression in rule["expr"]:
                    if "counter" in expression:
                        counts[rule["comment"]] = expression["counter"]
        return counts
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def owns_listeners(pid):
    """Readiness must not accept a port squatted by an untrusted task."""
    try:
        inodes = {os.readlink(fd) for fd in Path(f"/proc/{pid}/fd").iterdir()}
        found = set()
        for protocol in ("tcp", "udp"):
            for line in Path(f"/proc/net/{protocol}").read_text().splitlines()[1:]:
                fields = line.split()
                if f"socket:[{fields[9]}]" not in inodes:
                    continue
                address, port = fields[1].split(":")
                if address == "0100007F" and (protocol != "tcp" or fields[3] == "0A"):
                    found.add((protocol, int(port, 16)))
        return {("tcp", 12345), ("tcp", 1053), ("udp", 1053)} <= found
    except (OSError, IndexError):
        return False


def validate_upstream_namespace(settings):
    # The task shares the gateway's network namespace. It must not impersonate
    # either the proxy (credentials) or the direct resolver (destination IPs).
    import ipaddress
    direct = settings.get("transport") == "direct"
    addresses = settings["dns_servers"] if direct else [settings["upstream_ip"]]
    if not addresses:
        raise ValueError("upstream addresses are required")
    for value in addresses:
        host, separator, port = value.partition(":")
        address = ipaddress.IPv4Address(host)
        if direct and str(address) == "127.0.0.11":
            if separator and int(port) != 53:
                raise ValueError("Docker DNS requires port 53")
            continue
        if (address.is_loopback or address.is_unspecified or address.is_multicast
                or address.is_link_local or address.is_reserved):
            raise ValueError("upstream cannot be local/link-local/multicast")
        route = subprocess.run(["ip", "-4", "route", "get", str(address)], capture_output=True,
                               text=True, check=True, timeout=5).stdout.split()
        if not route or route[0] == "local":
            raise ValueError("upstream must be outside the shared task network namespace")


class Controller:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.worker = None
        self.generation = 0
        self.deadline_ns = 0
        self.public = False
        self.state = {"ready": False, "mode": "no-network"}

    def audit(self, event):
        print(json.dumps({"event": event, "instance": os.environ.get("SEARCHSWE_EGRESS_INSTANCE", "standalone"),
                          "generation": self.generation, "policy_sha256": self.state.get("policy_sha256"),
                          "packet_counters": packet_counters()}), flush=True)

    def refresh_lease(self, deadline_ns):
        remaining = lease_remaining(deadline_ns)
        # Read wall time BEFORE monotonic time: a pause between the reads can
        # only shorten this cutoff. The absolute cutoff prevents a queued nft
        # command from granting a fresh relative lease after a controller pause.
        cutoff = (time.time_ns() + deadline_ns - time.monotonic_ns()) // 10**9
        cutoff = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # Expiry is enforced by nftables even if the controller is SIGSTOPed.
        # One atomic transaction: never a permanently accepted mark.
        nft(f"flush set inet searchswe_egress leased_marks\n"
            f"add element inet searchswe_egress leased_marks {{ {MARK} timeout {remaining}ms"
            + (f", 0 timeout {remaining}ms" if self.public else "") + " }\n"
            "flush chain inet searchswe_egress lease\n"
            f'add rule inet searchswe_egress lease meta time < "{cutoff}" '
            "meta mark @leased_marks counter name proxy_packets accept\n")
        self.deadline_ns = deadline_ns

    def renew(self, deadline_ns):
        with self.lock:
            if not self.state.get("ready") or time.monotonic_ns() >= self.deadline_ns:
                self.fail("lease_expired")
                raise RuntimeError("an expired lease requires an explicit policy replacement")
            self.refresh_lease(deadline_ns)
            return self.state

    def stop_worker(self):
        worker, self.worker = self.worker, None
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=3)
        (RUN / "gost.json").unlink(missing_ok=True)

    def fail(self, reason="policy_failure"):
        try:
            close_gate()
        finally:
            try:
                self.stop_worker()
            finally:
                self.audit(reason)
                self.deadline_ns = 0
                self.state = {"ready": False, "error": reason, "generation": self.generation}

    def apply(self, requested):
        with self.lock:
            try:
                close_gate()
                self.audit("generation_closed")
                self.stop_worker()
                current = policy(requested["mode"], requested["hosts"],
                                 allow_public=self.settings.get("transport") == "direct")
                if self.settings.get("upstream_host") in current["hosts"]:
                    raise ValueError("a general proxy is not an API destination")
                self.public = current["mode"] == "public"
                install_rules(self.settings, public=self.public)
                deadline_ns = requested.get("deadline_ns", 0)
                lease_remaining(deadline_ns)
                self.generation += 1
                if current["mode"] == "allowlist" and current["hosts"]:
                    config = RUN / "gost.json"
                    config.write_text(json.dumps(gost_config(self.settings, current["hosts"])))
                    config.chmod(0o600)
                    self.worker = subprocess.Popen(["/bin/gost", "-C", str(config)],
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    deadline = time.monotonic() + 10
                    while True:
                        if self.worker.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("gateway worker failed readiness")
                        if owns_listeners(self.worker.pid):
                            break
                        time.sleep(.05)
                self.refresh_lease(deadline_ns)
                if self.worker is not None or self.public:
                    nft("delete table inet searchswe_guard\n")
                # Empty allowlist and no-network retain the closed guard and
                # have no proxy or DNS worker. Local application IPC remains.
                self.state = {"ready": True, **current, "generation": self.generation,
                              "policy_sha256": hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()}
                READY.touch()
                self.audit("generation_ready")
                return self.state
            except Exception:
                self.fail()
                raise

    def watch(self):
        while True:
            time.sleep(.1)
            with self.lock:
                if self.state.get("ready") and time.monotonic_ns() >= self.deadline_ns:
                    self.fail("lease_expired")
                elif self.worker is not None and self.worker.poll() is not None:
                    self.fail("worker_exit")


def serve():
    os.umask(0o077)
    RUN.mkdir(mode=0o700, exist_ok=True)
    close_gate()
    settings = json.loads(Path("/opt/searchswe/input.json").read_text())
    validate_upstream_namespace(settings)
    controller = Controller(settings)

    def shutdown(*_):
        with controller.lock:
            controller.fail()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                self.connection.settimeout(45)
                request = json.loads(self.rfile.readline(65537))
                if request == {"action": "show"}:
                    with controller.lock:
                        response = dict(controller.state)
                elif request.get("action") == "lease":
                    response = controller.renew(request["deadline_ns"])
                else:
                    response = controller.apply(request)
            except Exception:
                with controller.lock:
                    controller.fail()
                response = {"ready": False, "error": "gateway policy request failed"}
            try:
                self.wfile.write(json.dumps(response).encode() + b"\n")
            except OSError:
                with controller.lock:
                    controller.fail()

    initial = os.environ.get("EGRESS_CONTROL_INITIAL_NETWORK_MODE", "no-network")
    hosts = os.environ.get("EGRESS_CONTROL_INITIAL_ALLOWED_HOSTS", "").split()
    deadline = int(os.environ.get("SEARCHSWE_EGRESS_INITIAL_DEADLINE_NS", time.monotonic_ns() + LEASE_SECONDS * 10**9))
    controller.apply({"mode": initial, "hosts": hosts, "deadline_ns": deadline})
    CONTROL.unlink(missing_ok=True)
    server = socketserver.UnixStreamServer(str(CONTROL), Handler)
    threading.Thread(target=controller.watch, daemon=True).start()
    print("Search-SWE restricted gateway ready", flush=True)
    server.serve_forever()


def client(arguments):
    deadline_ns = time.monotonic_ns() + LEASE_SECONDS * 10**9
    if arguments[:1] == ["--deadline-ns"]:
        deadline_ns = int(arguments[1])
        arguments = arguments[2:]
    action = arguments[0] if arguments else "show"
    if action == "show":
        request = {"action": "show"}
    elif action == "allow":
        request = {"mode": "allowlist", "hosts": arguments[1:], "deadline_ns": deadline_ns}
    elif action == "deny-all":
        request = {"mode": "no-network", "hosts": [], "deadline_ns": deadline_ns}
    elif action == "allow-all":
        request = {"mode": "public", "hosts": [], "deadline_ns": deadline_ns}
    elif action == "lease":
        request = {"action": "lease", "deadline_ns": deadline_ns}
    else:
        raise ValueError("unsupported gateway command")
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(60)
        sock.connect(str(CONTROL))
        sock.sendall(json.dumps(request).encode() + b"\n")
        response = json.loads(sock.makefile("rb").readline(65537))
    print(json.dumps(response))
    if not response.get("ready"):
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        serve()
    else:
        client(sys.argv[1:])
