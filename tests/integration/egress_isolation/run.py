"""Offline UDP/IPv6/raw-capability/direct-proxy/cross-namespace gate."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time
import uuid

HERE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(HERE.parent / "egress_s0/run.py"))
docker, events, wait_ready = (helpers[n] for n in ("docker", "events", "wait_ready"))


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = "searchswe-isolation-" + uuid.uuid4().hex[:12]
    label = "searchswe.isolation=" + identity
    network, mock, gateway, target, control = (identity + s for s in ("", "-mock", "-gateway", "-target", "-control"))
    containers, networks = [], []
    result = {"status": "infrastructure_error", "identity": identity, "checks": [],
              "transport": args.transport,
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        images = {key: json.loads(docker("image", "inspect", value).stdout)[0]["Id"] for key, value in
                  [("gateway", args.gateway_image), ("python", args.python_image)]}
        result["images"] = images
        ula = "fd" + uuid.uuid4().hex[:2] + ":" + uuid.uuid4().hex[:4] + ":" + uuid.uuid4().hex[:4] + "::/64"
        docker("network", "create", "--internal", "--ipv6", "--subnet", ula, "--label", label, network)
        networks.append(network)
        mounts = []
        result["sources"] = {}
        for source, destination in [(HERE / "fixture.py", "fixture.py"), (HERE.parent / "egress_lifecycle/fixture.py", "lifecyclefixture.py"),
                                    (HERE.parent / "egress_s0/fixture.py", "s0fixture.py")]:
            mounts.extend(["-v", f"{source}:/{destination}:ro"])
            result["sources"][destination] = hashlib.sha256(source.read_bytes()).hexdigest()
        containers.append(mock)
        docker("run", "-d", "--pull", "never", "--name", mock, "--label", label, "--network", network,
               "--cap-drop", "ALL", *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py",
               "serve-direct" if args.transport == "direct" else "serve")
        wait_ready(mock)
        containers.append(control)
        docker("run", "-d", "--pull", "never", "--name", control, "--label", label, "--network", network,
               "--cap-drop", "NET_RAW", "--cap-drop", "NET_ADMIN", "--security-opt", "no-new-privileges:true",
               *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py", "idle")
        wait_ready(control)
        addresses = json.loads(docker("inspect", mock).stdout)[0]["NetworkSettings"]["Networks"][network]
        ip, ip6 = addresses["IPAddress"], addresses["GlobalIPv6Address"]
        if not ip6:
            raise RuntimeError("no IPv6 positive-control address")
        config = output / "input.json"
        settings = {"upstream_ip": ip, "upstream_port": 18080, "upstream_addr": f"{ip}:18080",
                    "upstream_host": ip, "upstream_tls": False, "doh_url": "tcp://resolver.example:15353"}
        if args.transport == "direct":
            settings = {"transport": "direct", "dns_servers": [ip]}
        config.write_text(json.dumps(settings))
        config.chmod(0o600)
        containers.append(gateway)
        docker("run", "-d", "--pull", "never", "--name", gateway, "--label", label, "--network", network,
               "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", "--cap-add", "DAC_OVERRIDE",
               "--sysctl", "net.ipv6.conf.all.disable_ipv6=1", "--sysctl", "net.ipv6.conf.default.disable_ipv6=1",
               "-v", f"{config}:/opt/searchswe/input.json:ro", "--entrypoint", "/opt/egress-sidecar/entrypoint.sh", images["gateway"])
        for _ in range(30):
            if docker("exec", gateway, "network-policy", "show", check=False).returncode == 0:
                break
            time.sleep(.1)
        else:
            raise RuntimeError("gateway failed startup")
        docker("exec", gateway, "network-policy", "allow", "allowed.example")
        containers.append(target)
        docker("run", "-d", "--pull", "never", "--name", target, "--label", label, "--network", "container:" + gateway,
               "--cap-drop", "NET_RAW", "--cap-drop", "NET_ADMIN", "--security-opt", "no-new-privileges:true", *mounts,
               "--entrypoint", "python", images["python"], "-u", "/fixture.py", "target")
        wait_ready(target)
        gateway_ip = json.loads(docker("inspect", gateway).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]

        def probe(case, address, expected, *, confined=True, observer=mock):
            docker("exec", gateway, "network-policy", "lease")
            before = len(events(observer))
            response = docker("exec", target if confined else control, "python", "/fixture.py", case, address,
                              check=False, timeout=20)
            time.sleep(.2)
            # An expired lease must not turn a failed positive infrastructure
            # into an apparently successful security negative.
            docker("exec", gateway, "network-policy", "lease")
            observed = events(observer)[before:]
            if response.returncode:
                raise RuntimeError("isolation client fixture failed")
            if any(e.get("kind") == "fixture_error" for e in observed):
                raise RuntimeError("isolation upstream fixture failed")
            passed = bool(observed) == expected
            if case == "api" and expected:
                passed = passed and any(e.get("kind") == "http" for e in observed)
            if case == "capabilities":
                passed = passed and "raw sockets denied" in response.stdout
            result["checks"].append({"case": case, "confined": confined, "passed": passed,
                                     "upstream_events": observed, "client": response.stdout.strip()})
            if not passed:
                if expected:
                    raise RuntimeError("isolation positive control failed")
                result["status"] = "security_gate_failed"
                raise RuntimeError("forbidden isolation traffic reached target")

        probe("proxy-allow", ip, True, confined=False)
        probe("api", ip, True)
        probe("proxy-deny", ip, False)
        probe("metadata", ip, False)
        probe("udp", ip, True, confined=False)
        probe("udp", ip, False)
        probe("ipv6", ip6, True, confined=False)
        probe("ipv6", ip6, False)
        probe("capabilities", ip, False)
        probe("cross", "127.0.0.1", True, observer=target)
        probe("cross", gateway_ip, False, confined=False, observer=target)
        probe("api", ip, True)
        result["status"] = "passed"
    except Exception as error:
        result["error"] = str(error)
    finally:
        errors = []
        for name in reversed(containers):
            inspected = docker("inspect", name, check=False)
            if inspected.returncode:
                continue
            info = json.loads(inspected.stdout)[0]
            if info["Config"].get("Labels", {}).get("searchswe.isolation") != identity:
                errors.append("ownership mismatch")
                continue
            logs = docker("logs", name, check=False)
            (output / (name.removeprefix(identity + "-") + ".log")).write_text(logs.stdout + logs.stderr)
            if docker("rm", "-f", name, check=False).returncode:
                errors.append("container cleanup failed")
        for name in networks:
            if docker("network", "rm", name, check=False).returncode:
                errors.append("network cleanup failed")
        result["cleanup_errors"] = errors
        if errors:
            result["status"] = "cleanup_error"
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "error": result.get("error"), "output": str(output)}))
    return 0 if result["status"] == "passed" else 1 if result["status"] == "security_gate_failed" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--python-image", default="python:3.13-slim")
    parser.add_argument("--transport", choices=("proxy", "direct"), default="proxy")
    parser.add_argument("--output", required=True, type=Path)
    raise SystemExit(run(parser.parse_args()))
