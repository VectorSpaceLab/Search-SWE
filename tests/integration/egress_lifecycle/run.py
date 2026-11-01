"""Offline S1 controller integration; no Harbor adapter or real API claims."""

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import runpy
import time
import uuid


S0 = Path(__file__).resolve().parents[1] / "egress_s0"
FIXTURE = Path(__file__).with_name("fixture.py")
helpers = runpy.run_path(str(S0 / "run.py"))
docker, events, wait_ready = (helpers[name] for name in ("docker", "events", "wait_ready"))


class SecurityGateFailure(RuntimeError):
    pass


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = "searchswe-lifecycle-" + uuid.uuid4().hex[:12]
    network, mock, gateway = identity, identity + "-mock", identity + "-gateway"
    containers = []
    created_network = False
    result = {"status": "infrastructure_error", "checks": [], "identity": identity,
              "transport": args.transport, "dns_source": args.dns_source}
    try:
        images = {role: json.loads(docker("image", "inspect", image).stdout)[0]["Id"]
                  for role, image in [("gateway", args.gateway_image), ("python", args.python_image)]}
        result["images"] = images
        result["fixture_sha256"] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        docker("network", "create", "--internal", "--label", f"searchswe.lifecycle={identity}", network)
        created_network = True
        containers.append(mock)
        common = ["--pull", "never", "--label", f"searchswe.lifecycle={identity}"]
        mounts = ["-v", f"{FIXTURE}:/fixture.py:ro", "-v", f"{S0 / 'fixture.py'}:/s0fixture.py:ro"]
        docker("run", "-d", "--name", mock, "--network", network,
               "--network-alias", "allowed.example", "--network-alias", "blocked.example", "--cap-drop", "ALL", *common,
               *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py",
               "serve-direct" if args.transport == "direct" else "serve")
        wait_ready(mock)
        ip = json.loads(docker("inspect", mock).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        if args.transport == "direct":
            ipam = json.loads(docker("network", "inspect", network).stdout)[0]["IPAM"]["Config"]
            subnet = next(ipaddress.IPv4Network(row["Subnet"]) for row in ipam if ":" not in row["Subnet"])
            local_ip = str(subnet.network_address + 10)
            for suffix, address, error in (("self-dns", local_ip, "outside the shared task network namespace"),
                                            ("fake-docker-dns", "127.0.0.11:5353", "Docker DNS requires port 53")):
                bad_gateway = identity + "-" + suffix
                bad_config = output / (suffix + ".json")
                bad_config.write_text(json.dumps({"transport": "direct", "dns_servers": [address]}))
                bad_config.chmod(0o600)
                containers.append(bad_gateway)
                docker("run", "-d", "--name", bad_gateway, "--network", network,
                       *(["--ip", local_ip] if suffix == "self-dns" else []),
                       "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", *common,
                       "-v", f"{bad_config}:/opt/searchswe/input.json:ro",
                       "--entrypoint", "/opt/egress-sidecar/entrypoint.sh", images["gateway"])
                status = docker("wait", bad_gateway, timeout=20).stdout.strip()
                log = docker("logs", bad_gateway)
                if status == "0" or error not in log.stdout + log.stderr:
                    raise SecurityGateFailure("task-owned DNS endpoint was not rejected at gateway startup")
                result["checks"].append({"case": suffix + "-rejected-before-task-start", "passed": True})
        settings = {"upstream_ip": ip, "upstream_port": 18080, "upstream_addr": f"{ip}:18080",
                    "upstream_host": ip, "upstream_tls": False, "doh_url": "tcp://resolver.example:15353"}
        if args.transport == "direct":
            settings = {"transport": "direct", "dns_servers": ["127.0.0.11" if args.dns_source == "docker" else ip]}
        config = output / "input.json"
        config.write_text(json.dumps(settings))
        config.chmod(0o600)
        containers.append(gateway)
        docker("run", "-d", "--name", gateway, "--network", network, "--cap-drop", "ALL",
               "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", "--cap-add", "KILL", *common,
               "-v", f"{config}:/opt/searchswe/input.json:ro", "--entrypoint", "/opt/egress-sidecar/entrypoint.sh",
               images["gateway"])
        for _ in range(50):
            status = docker("exec", gateway, "network-policy", "show", check=False)
            if status.returncode == 0:
                break
            time.sleep(.1)
        else:
            raise RuntimeError("controller did not start")
        client = identity + "-client"
        containers.append(client)
        docker("run", "-d", "--name", client, "--network", f"container:{gateway}",
               "--cap-drop", "NET_RAW", "--cap-drop", "NET_ADMIN", "--security-opt", "no-new-privileges:true",
               *common, *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py", "idle")
        wait_ready(client)

        def change(*args):
            response = docker("exec", gateway, "network-policy", *args)
            state = json.loads(response.stdout)
            result.setdefault("transitions", []).append(state)
            return state

        def probe(case, expected, renew=True):
            if renew:
                response = docker("exec", gateway, "network-policy", "lease", check=False)
                if expected and response.returncode:
                    raise RuntimeError("positive-control lease is unavailable")
            before = len(events(mock))
            if args.dns_source == "docker" and case.startswith("dns-"):
                response = docker("exec", client, "python", "/fixture.py", "dns-probe", case, timeout=15)
                evidence = json.loads(response.stdout)
                if (evidence["answers"] > 0) != expected:
                    raise SecurityGateFailure("Docker DNS response violated phase policy")
                result["checks"].append({"case": case, "passed": True, **evidence})
                return
            response = docker("exec", client, "python", "/s0fixture.py", case, ip, timeout=15)
            time.sleep(.2)
            observed = events(mock)[before:]
            reached = any(e.get("kind") in {"connect", "dns", "http"} for e in observed)
            valid_positive = any(e.get("kind") == ("dns" if case.startswith("dns-") else "http") for e in observed)
            passed = reached == expected and (not expected or valid_positive)
            if any(e.get("kind") == "fixture_error" for e in observed):
                raise RuntimeError("mock upstream fixture failed")
            result["checks"].append({"case": case, "passed": passed, "upstream_events": observed,
                                     "expected_upstream": expected,
                                     "client_output": response.stdout.strip()})
            if not passed:
                if expected:
                    raise RuntimeError(f"positive control failed: {case}")
                raise SecurityGateFailure(f"forbidden request reached upstream: {case}")

        def hold(suffix, public=False):
            name = identity + "-" + suffix
            containers.append(name)
            docker("run", "-d", "--name", name, "--network", f"container:{gateway}", "--cap-drop", "ALL",
                   *common, *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py", "wait-held", ip)
            for _ in range(50):
                if any(e.get("kind") == "started" for e in events(name)):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("held actor failed to start")
            deadline = time.monotonic_ns() + 30 * 10**9
            change("--deadline-ns", str(deadline), *( ["allow-all"] if public else ["allow", "allowed.example"]))
            docker("exec", name, "touch", "/tmp/begin")
            wait_ready(name)
            return name, deadline

        change("allow", "allowed.example")
        capability = docker("exec", client, "python", "/s0fixture.py", "capability", ip)
        if "SO_MARK denied" not in capability.stdout:
            raise SecurityGateFailure("root task can mark its own egress sockets")
        result["checks"].append({"case": "root-so-mark-denied", "passed": True})
        probe("http-allow", True)
        probe("http-deny", False)
        probe("dns-allow", True)
        probe("dns-chaos", False)
        if args.transport == "direct":
            change("allow-all")
            probe("http-deny", True)
            def embedded_dns(expected):
                response = docker("exec", client, "python", "/fixture.py", "dns-probe", "docker-dns-bypass")
                evidence = json.loads(response.stdout)
                if (evidence["answers"] > 0) != expected:
                    raise SecurityGateFailure("embedded DNS bypass control failed")
                result["checks"].append({"case": "embedded-dns-public-positive" if expected else "embedded-dns-bypass-denied",
                                         "passed": True, **evidence})
            embedded_dns(True)
            public_held, _ = hold("public-held", public=True)
            change("allow", "allowed.example")
            before = len(events(mock))
            docker("exec", public_held, "touch", "/tmp/release")
            if docker("wait", public_held, timeout=10).stdout.strip() != "0" or events(mock)[before:]:
                raise SecurityGateFailure("old raw public connection survived restriction")
            result["checks"].append({"case": "public-connection-revoked-by-allowlist", "passed": True})
            embedded_dns(False)
            probe("http-deny", False)
            probe("http-allow", True)
            probe("dns-deny", False)
        # Prove that the SAME idle connection can outlive the lease interval
        # when the host renews. Otherwise an origin/proxy idle timeout could
        # masquerade as the later frozen-controller old-socket revocation.
        idle_control, _ = hold("idle-control")
        time.sleep(16)
        docker("exec", gateway, "network-policy", "lease")
        time.sleep(17)
        before = len(events(mock))
        docker("exec", idle_control, "touch", "/tmp/release")
        if docker("wait", idle_control, timeout=15).stdout.strip() != "0":
            raise RuntimeError("long-idle positive client failed")
        observed = events(mock)[before:]
        if not any(e.get("kind") == "http" and e.get("request") == "GET /held HTTP/1.1" for e in observed):
            raise RuntimeError("long-idle connection positive control failed")
        result["checks"].append({"case": "idle-connection-outlives-lease-with-renewal", "passed": True,
                                 "upstream_events": observed})
        # Keep an acknowledged real upstream HTTP connection across revocation.
        held, _ = hold("held")
        change("deny-all")
        before = len(events(mock))
        docker("exec", held, "touch", "/tmp/release")
        exited = docker("wait", held, timeout=10)
        if exited.stdout.strip() != "0":
            raise RuntimeError("held client failed")
        time.sleep(.2)
        observed = events(mock)[before:]
        passed = not observed
        result["checks"].append({"case": "existing-connection-revoked", "passed": passed,
                                 "upstream_events": observed})
        if not passed:
            raise SecurityGateFailure("old connection remained authorized")
        probe("http-allow", False)
        change("allow", "allowed.example")
        probe("http-allow", True)
        # Invalid replacement must not leave the previous permissive worker.
        response = docker("exec", gateway, "network-policy", "allow", "*.example", check=False)
        if response.returncode == 0:
            raise RuntimeError("invalid policy accepted")
        probe("http-allow", False)
        change("allow", "allowed.example")
        probe("http-allow", True)
        docker("exec", gateway, "sh", "-c", "kill -9 $(pidof gost)")
        for _ in range(50):
            if docker("exec", gateway, "network-policy", "show", check=False).returncode:
                break
            time.sleep(.1)
        else:
            raise RuntimeError("worker crash did not invalidate readiness")
        probe("http-allow", False)
        change("allow", "allowed.example")
        probe("http-allow", True)
        # Readiness must not mistake a task-owned listener for the new worker.
        change("deny-all")
        squatter = identity + "-squatter"
        containers.append(squatter)
        docker("run", "-d", "--name", squatter, "--network", f"container:{gateway}", "--cap-drop", "ALL",
               *common, *mounts, "--entrypoint", "python", images["python"], "-u", "/fixture.py", "squat")
        wait_ready(squatter)
        response = docker("exec", gateway, "network-policy", "allow", "allowed.example", check=False)
        if response.returncode == 0:
            raise SecurityGateFailure("task-owned listener was accepted as gateway readiness")
        probe("http-allow", False)
        result["checks"][-1]["case"] = "task-listener-cannot-fake-readiness"
        docker("rm", "-f", squatter)
        change("allow", "allowed.example")
        probe("http-allow", True)
        # Freeze only the controller (PID 1), not the proxy worker. The kernel
        # lease, independent of the Python watchdog, must revoke egress.
        frozen_held, deadline = hold("frozen-held")
        probe("http-allow", True, renew=False)
        docker("kill", "--signal=STOP", gateway)
        docker("exec", gateway, "python3", "-c", "from pathlib import Path; import subprocess; "
               "pid=subprocess.check_output(['pidof','gost'],text=True).strip(); "
               "assert Path('/proc/'+pid+'/stat').read_text().split()[2] not in {'T','t','Z'}")
        time.sleep(max(0, (deadline - time.monotonic_ns()) / 10**9) + .3)
        probe("http-allow", False, renew=False)
        result["checks"][-1]["case"] = "kernel-lease-controller-frozen"
        before = len(events(mock))
        docker("exec", frozen_held, "touch", "/tmp/release")
        if docker("wait", frozen_held, timeout=15).stdout.strip() != "0":
            raise RuntimeError("frozen held client failed")
        observed = events(mock)[before:]
        if observed:
            raise SecurityGateFailure("old connection survived the kernel lease")
        result["checks"].append({"case": "old-connection-kernel-lease-controller-frozen", "passed": True,
                                 "upstream_events": observed})
        docker("kill", "--signal=CONT", gateway)
        response = docker("exec", gateway, "network-policy", "--deadline-ns", str(deadline),
                          "allow", "allowed.example", check=False)
        if response.returncode == 0:
            raise SecurityGateFailure("stale host command reopened an expired generation")
        probe("http-allow", False)
        result["checks"][-1]["case"] = "expired-command-cannot-reopen"
        change("allow", "allowed.example")
        probe("http-allow", True)
        if args.transport == "direct":
            public_held, deadline = hold("public-frozen-held", public=True)
            docker("kill", "--signal=STOP", gateway)
            time.sleep(max(0, (deadline - time.monotonic_ns()) / 10**9) + .3)
            probe("http-allow", False, renew=False)
            result["checks"][-1]["case"] = "public-kernel-lease-controller-frozen"
            before = len(events(mock))
            docker("exec", public_held, "touch", "/tmp/release")
            if docker("wait", public_held, timeout=10).stdout.strip() != "0" or events(mock)[before:]:
                raise SecurityGateFailure("old public connection survived expired kernel lease")
            result["checks"].append({"case": "old-public-connection-kernel-lease", "passed": True})
            docker("kill", "--signal=CONT", gateway)
            change("allow", "allowed.example")
            probe("http-allow", True)
        result["status"] = "passed"
        return 0
    except SecurityGateFailure as error:
        result["status"] = "security_gate_failed"
        result["error"] = str(error)
        return 1
    except Exception as error:
        result["error"] = str(error)
        return 2
    finally:
        errors = []
        for name in reversed(containers):
            inspected = docker("inspect", name, check=False)
            if inspected.returncode:
                continue
            info = json.loads(inspected.stdout)[0]
            if info["Config"].get("Labels", {}).get("searchswe.lifecycle") != identity:
                errors.append(f"ownership mismatch: {name}")
                continue
            log = docker("logs", name, check=False)
            (output / f"{name.removeprefix(identity + '-')}.log").write_text(log.stdout + log.stderr)
            if name == gateway:
                rules = docker("exec", gateway, "nft", "list", "ruleset", check=False)
                (output / "rules.nft").write_text(rules.stdout + rules.stderr)
            if docker("rm", "-f", name, check=False).returncode:
                errors.append(f"container cleanup failed: {name}")
        if created_network and docker("network", "rm", network, check=False).returncode:
            errors.append("network cleanup failed")
        result["cleanup_errors"] = errors
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "error": result.get("error"), "output": str(output)}))
        if errors:
            raise RuntimeError("lifecycle cleanup incomplete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--python-image", default="python:3.13-slim")
    parser.add_argument("--transport", choices=("proxy", "direct"), default="proxy")
    parser.add_argument("--dns-source", choices=("fixture", "docker"), default="fixture")
    parser.add_argument("--output", required=True, type=Path)
    raise SystemExit(run(parser.parse_args()))
