"""Explicit, offline release gate for Harbor's GOST candidate (not runtime).

Requires preloaded images; never pulls, publishes ports, or calls external APIs.
Exit 1 means a negative probe reached the mock upstream; exit 2 means test error.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid


FIXTURE = Path(__file__).with_name("fixture.py").resolve()


def docker(*args, check=True, timeout=60):
    return subprocess.run(["docker", *args], check=check, text=True,
                          capture_output=True, timeout=timeout)


def events(name):
    return [json.loads(line) for line in docker("logs", name).stdout.splitlines() if line.startswith("{")]


def wait_ready(name):
    for _ in range(50):
        if any(e.get("kind") == "ready" for e in events(name)):
            return
        time.sleep(.1)
    raise RuntimeError("mock upstream did not become ready")


def configuration(upstream):
    return {
        "log": {"level": "error"},
        "services": [
            {"name": "transparent", "addr": ":12345", "bypass": "policy",
             "metadata": {"so_mark": "114514"},
             "handler": {"type": "red", "chain": "upstream", "metadata": {
                 "sniffing": True, "sniffing.timeout": "2s", "sniffing.fallback": False}},
             "listener": {"type": "red"}},
            {"name": "dns", "addr": "127.0.0.1:1053", "bypass": "policy",
             "metadata": {"so_mark": "114514"},
             "handler": {"type": "dns", "metadata": {
                 "dns": f"tcp://{upstream}:15353", "timeout": "2s"}},
             "listener": {"type": "dns", "metadata": {"mode": "tcp"}}},
        ],
        "bypasses": [{"name": "policy", "whitelist": True, "matchers": ["allowed.example"]}],
        "chains": [{"name": "upstream", "hops": [{"name": "proxy", "nodes": [
            {"name": "mock", "addr": f"{upstream}:18080", "metadata": {"so_mark": "114514"},
             "connector": {"type": "http"}, "dialer": {"type": "tcp"}},
        ]}]}],
    }


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = "searchswe-s0-" + uuid.uuid4().hex[:12]
    network, mock, gateway = identity, identity + "-mock", identity + "-gateway"
    containers = []
    created_network = False
    result = {"status": "infrastructure_error", "checks": [], "identity": identity}
    try:
        # Capture immutable IDs, and run those IDs rather than mutable tags.
        images = {}
        for role, image in [("gost", args.gost_image), ("python", args.python_image)]:
            images[role] = json.loads(docker("image", "inspect", image).stdout)[0]["Id"]
        result["images"] = images
        result["fixture_sha256"] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        docker("network", "create", "--internal", "--label", f"searchswe.s0={identity}", network)
        created_network = True
        containers.append(mock)
        docker("run", "-d", "--pull", "never", "--name", mock, "--network", network,
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
               "--label", f"searchswe.s0={identity}",
               "-v", f"{FIXTURE}:/fixture.py:ro", "--entrypoint", "python",
               images["python"], "-u", "/fixture.py", "serve")
        wait_ready(mock)
        info = json.loads(docker("inspect", mock).stdout)[0]
        upstream = info["NetworkSettings"]["Networks"][network]["IPAddress"]
        config = output / "gost.json"
        config.write_text(json.dumps(configuration(upstream), indent=2) + "\n")
        containers.append(gateway)
        docker("run", "-d", "--pull", "never", "--name", gateway, "--network", network,
               "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
               "--label", f"searchswe.s0={identity}",
               "-v", f"{config}:/gost.json:ro", "--entrypoint", "/bin/gost",
               images["gost"], "-C", "/gost.json")
        # Apply the image's original Harbor redirect/filter rules. Static policy
        # in this candidate configuration equals the file policy in this helper.
        docker("exec", gateway, "network-policy", "allow", "allowed.example")
        client = identity + "-client"
        containers.append(client)
        docker("run", "-d", "--pull", "never", "--name", client,
               "--network", f"container:{gateway}", "--cap-drop", "NET_RAW",
               "--cap-drop", "NET_ADMIN", "--security-opt", "no-new-privileges:true",
               "--label", f"searchswe.s0={identity}", "-v", f"{FIXTURE}:/fixture.py:ro",
               "--entrypoint", "sleep", images["python"], "infinity")
        for case, expected in [
            ("capability", False), ("http-allow", True), ("http-deny", False),
            ("h2-allow", True), ("h2-deny", False), ("dns-allow", True),
            ("dns-deny", False), ("dns-chaos", False), ("dns-multiple", False),
            ("dns-hesiod", False), ("dns-any-class", False),
            ("h2-multiple", True), ("tls-allow", True), ("tls-deny", False),
            ("tls-no-sni", False), ("http-ip", False), ("unknown-protocol", False),
            ("http-connect-mismatch", False), ("http-absolute-mismatch", False),
            ("dns-txt", False), ("dns-answer", False), ("dns-authority", False),
            ("dns-extra", False), ("dns-edns-payload", False),
        ]:
            before = len(events(mock))
            response = docker(
                "exec", client, "python", "/fixture.py", case, upstream,
                timeout=30, check=False)
            if response.returncode:
                raise RuntimeError(f"client {case} failed: {response.stderr}")
            # Bounded observation window, not a substitute for positive controls.
            time.sleep(.2)
            observed = events(mock)[before:]
            if any(e.get("kind") == "fixture_error" for e in observed):
                raise RuntimeError(f"mock upstream failed during {case}")
            reached = any(e.get("kind") in {"connect", "dns"} for e in observed)
            # Multi-stream positives must not hide a forbidden second target.
            forbidden = [e for e in observed if (
                e.get("kind") == "connect" and e.get("request") != "CONNECT allowed.example:443 HTTP/1.1"
            ) or (e.get("kind") == "dns" and any(q["name"] != "allowed.example" or q["class"] != 1
                                                 for q in e["questions"]))]
            passed = reached == expected and not forbidden
            if case == "capability":
                passed = passed and "SO_MARK denied" in response.stdout
            result["checks"].append({"case": case, "passed": passed,
                                     "expected_upstream": expected, "upstream_events": observed,
                                     "client_output": response.stdout.strip()})
            print(f"{case}: {'PASS' if passed else 'FAIL'}", flush=True)
            if expected and not passed:
                raise RuntimeError(f"positive control {case} failed; no security conclusion")
        positives = [c for c in result["checks"] if c["expected_upstream"]]
        if not all(c["passed"] for c in positives):
            raise RuntimeError("positive control failed; no security conclusion")
        result["status"] = "passed" if all(c["passed"] for c in result["checks"]) else "security_gate_failed"
        return 0 if result["status"] == "passed" else 1
    except Exception as error:
        result["error"] = str(error)
        return 2
    finally:
        cleanup_errors = []
        for name in reversed(containers):
            inspected = docker("container", "inspect", name, check=False)
            if inspected.returncode:
                continue
            info = json.loads(inspected.stdout)[0]
            if info["Config"].get("Labels", {}).get("searchswe.s0") != identity:
                cleanup_errors.append(f"ownership mismatch: {name}")
                continue
            if name in {gateway, mock}:
                log = docker("logs", name, check=False)
                (output / f"{'gateway' if name == gateway else 'upstream'}.log").write_text(log.stdout + log.stderr)
            removed = docker("rm", "-f", name, check=False)
            if removed.returncode:
                cleanup_errors.append(f"container cleanup failed: {name}")
        if created_network:
            removed = docker("network", "rm", network, check=False)
            if removed.returncode:
                cleanup_errors.append(f"network cleanup failed: {network}")
        result["cleanup_errors"] = cleanup_errors
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        if cleanup_errors:
            raise RuntimeError("S0 cleanup incomplete; see result.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gost-image", required=True, help="Preloaded Harbor sidecar image containing network-policy")
    parser.add_argument("--python-image", default="python:3.13-slim")
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory; must not exist")
    raise SystemExit(run(parser.parse_args()))
