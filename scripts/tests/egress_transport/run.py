"""Offline TLS/auth/DoH integration. No public API, DNS or published port."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).with_name("fixture.go")
helpers = runpy.run_path(str(Path(__file__).parents[1] / "egress_s0/run.py"))
docker, events, wait_ready = (helpers[n] for n in ("docker", "events", "wait_ready"))


class GateFailure(RuntimeError):
    pass


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = "searchswe-transport-" + uuid.uuid4().hex[:12]
    label = "searchswe.transport=" + identity
    network, mock, image_tag = identity, identity + "-mock", identity + ":ca"
    containers, networks = [], []
    created_image = False
    private = tempfile.TemporaryDirectory(prefix="searchswe-transport-")
    secret = Path(private.name)
    username, password = "user-" + uuid.uuid4().hex, "canary-" + uuid.uuid4().hex
    needles = [username, password, base64.b64encode(f"{username}:{password}".encode()).decode()]
    result = {"status": "infrastructure_error", "identity": identity, "checks": [],
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    try:
        version = subprocess.check_output([str(args.go.resolve()), "version"], text=True)
        if "go1.26.8 linux/amd64" not in version:
            raise RuntimeError("Use the pinned Linux amd64 Go 1.26.8 toolchain")
        binary = output / "fixture"
        subprocess.run([str(args.go.resolve()), "build", "-trimpath", "-buildvcs=false", "-o", str(binary), str(SOURCE)],
                       env={**os.environ, "CGO_ENABLED": "0", "GOTOOLCHAIN": "local", "GOMAXPROCS": "4",
                            "GOCACHE": str(ROOT / "jobs/egress-build/gocache")}, check=True, timeout=180)
        result["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        base = json.loads(docker("image", "inspect", args.gateway_image).stdout)[0]
        python = json.loads(docker("image", "inspect", args.python_image).stdout)[0]["Id"]
        result["base_image"] = base["Id"]
        def openssl(*arguments):
            subprocess.run(["openssl", *arguments], cwd=secret, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=SearchSWE fixture CA",
                "-keyout", "ca.key", "-out", "ca.crt")
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=proxy.example", "-keyout", "server.key", "-out", "server.csr")
        (secret / "extensions").write_text("subjectAltName=DNS:proxy.example,DNS:resolver.example,DNS:allowed.example\n")
        openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial",
                "-days", "1", "-extfile", "extensions", "-out", "server.crt")
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=resolver.example",
                "-addext", "subjectAltName=DNS:resolver.example", "-keyout", "bad.key", "-out", "bad.crt")
        (secret / "ca.crt").chmod(0o644)
        context = secret / "image"
        context.mkdir()
        (context / "ca.crt").write_bytes((secret / "ca.crt").read_bytes())
        (context / "Dockerfile").write_text(
            'ARG BASE\nFROM ${BASE}\nCOPY ca.crt /usr/local/share/ca-certificates/searchswe-fixture.crt\n'
            'RUN python3 -c "from pathlib import Path; p=Path(\'/etc/ssl/certs/ca-certificates.crt\'); '
            'p.write_bytes(p.read_bytes()+Path(\'/usr/local/share/ca-certificates/searchswe-fixture.crt\').read_bytes())"\n'
            f'LABEL searchswe.transport="{identity}"\n')
        built = docker("build", "--pull=false", "--network=none", "--build-arg", "BASE=" + args.gateway_image,
                       "-t", image_tag, str(context), timeout=120, check=False)
        (output / "image-build.log").write_text(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError("Fixture CA image build failed; inspect image-build.log")
        created_image = True
        image = json.loads(docker("image", "inspect", image_tag).stdout)[0]
        if image["RootFS"]["Layers"][:len(base["RootFS"]["Layers"])] != base["RootFS"]["Layers"]:
            raise RuntimeError("Fixture CA image does not extend the inspected base")
        result["fixture_image"] = image["Id"]
        docker("network", "create", "--internal", "--label", label, network)
        networks.append(network)
        mock_settings = secret / "mock.json"
        mock_settings.write_text(json.dumps({"username": username, "password": password,
                                            "cert": "/private/server.crt", "key": "/private/server.key"}))
        mock_settings.chmod(0o600)
        mounts = ["-v", f"{binary}:/fixture:ro", "-v", f"{secret / 'ca.crt'}:/public/ca.crt:ro"]
        containers.append(mock)
        docker("run", "-d", "--pull", "never", "--name", mock, "--label", label,
               "--network", network, "--cap-drop", "ALL", *mounts, "-v", f"{secret}:/private:ro",
               "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", "/fixture", python, "serve", "/private/mock.json")
        wait_ready(mock)
        ip = json.loads(docker("inspect", mock).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        common = {"upstream_ip": ip, "upstream_port": 18480, "upstream_addr": f"{ip}:18480",
                  "upstream_host": "proxy.example", "upstream_tls": True,
                  "auth": {"username": username, "password": password}, "doh_url": "https://resolver.example/dns-query"}

        clients = {}
        file_event_sources = set()
        def observe(name):
            if name in file_event_sources:
                text = docker("exec", name, "cat", "/tmp/events.jsonl").stdout
                return [json.loads(line) for line in text.splitlines() if line.strip()]
            return events(name)
        def prepare_client(gateway):
            name = identity + "-client-" + uuid.uuid4().hex[:8]
            containers.append(name)
            docker("run", "-d", "--pull", "never", "--name", name,
                   "--label", label, "--network", "container:" + gateway, "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges:true", *mounts, "--entrypoint", "sleep", python, "infinity")
            clients[gateway] = name

        def start(case, overrides=None, trusted_ca=True):
            name = identity + "-" + case
            settings = {**common, **(overrides or {})}
            config = secret / (case + ".json")
            config.write_text(json.dumps(settings))
            config.chmod(0o600)
            containers.append(name)
            docker("run", "-d", "--pull", "never", "--name", name, "--label", label,
                   "--network", network, "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
                   "--cap-add", "DAC_OVERRIDE", "--security-opt", "no-new-privileges:true", "--read-only",
                   "--tmpfs", "/run/searchswe:mode=0700", "--tmpfs", "/tmp:mode=1777",
                   "-v", f"{config}:/opt/searchswe/input.json:ro", "--entrypoint", "/opt/egress-sidecar/entrypoint.sh",
                   image["Id"] if trusted_ca else base["Id"])
            for _ in range(30):
                if docker("exec", name, "network-policy", "show", check=False).returncode == 0:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("gateway failed startup")
            # Provision potentially slow Docker actors before granting a lease.
            prepare_client(name)
            docker("exec", name, "network-policy", "allow", "allowed.example", "nx.example", "redirect.example", "timeout.example")
            return name

        def invoke(gateway, mode="get", destination=None, detached=False):
            arguments = ([mode, *destination] if mode.startswith("dns-") else
                         [mode, destination] if mode == "resolve" else [mode, destination or ip, "/public/ca.crt"])
            if detached:
                name = identity + "-client-" + uuid.uuid4().hex[:8]
                containers.append(name)
                response = docker("run", "-d", "--pull", "never", "--name", name,
                                  "--label", label, "--network", "container:" + gateway, "--cap-drop", "ALL",
                                  "--security-opt", "no-new-privileges:true", *mounts,
                                  "--entrypoint", "/fixture", python, "delayed-" + arguments[0], *arguments[1:], timeout=60)
                for _ in range(50):
                    if any(e.get("kind") == "started" for e in events(name)):
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError("held client did not start")
                docker("exec", gateway, "network-policy", "allow", "allowed.example")
                docker("exec", name, "touch", "/tmp/begin")
                return name, response
            docker("exec", gateway, "network-policy", "lease")
            name = clients[gateway]
            response = docker("exec", name, "/fixture", *arguments, check=False, timeout=20)
            return name, response

        def check(case, gateway, *, mode="get", destination=None, positive=False, deny_kinds=(), event_source=mock,
                  dns_expected=None):
            before = len(observe(event_source))
            _, response = invoke(gateway, mode, destination)
            docker("exec", gateway, "network-policy", "lease")
            observed = observe(event_source)[before:]
            has_api = any(e["kind"] == "api" for e in observed)
            if positive and (response.returncode or not has_api):
                raise RuntimeError("transport positive control failed: " + case)
            if any(e["kind"] in deny_kinds for e in observed):
                raise GateFailure("forbidden upstream event: " + case)
            if dns_expected is not None:
                if response.returncode or f'"ok":{str(dns_expected).lower()}' not in response.stdout:
                    raise RuntimeError("DNS fixture result mismatch: " + case)
                if dns_expected and not any(e.get("kind") == "dns" and e.get("name") == destination[1] for e in observed):
                    raise RuntimeError("DNS positive never reached DoH: " + case)
            result["checks"].append({"case": case, "passed": True, "upstream_events": observed,
                                     "client": response.stdout.strip(), "returncode": response.returncode})

        good = start("good")
        check("tls-proxy-auth-api-h2", good, positive=True)
        if not any(e.get("protocol") == "HTTP/2.0" for e in events(mock)):
            raise RuntimeError("HTTP/2 positive control was not negotiated")
        check("approved-private-endpoint-preserves-port", good, mode="get-alt-port", positive=True)
        if not any(e.get("target") == "allowed.example:8443" for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("approved API port was not preserved")
        check("docker-dns-doh-api", good, destination="-", positive=True)
        if not any(e["kind"] == "dns" for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("system DNS positive did not traverse DoH")
        for entry, server in (("local", "127.0.0.1:1053"), ("explicit", ip + ":53"), ("docker", "127.0.0.11:53")):
            for protocol in ("tcp", "udp"):
                for family in ("ip4", "ip6"):
                    docker("exec", good, "network-policy", "allow", "allowed.example")
                    mode = f"dns-{protocol}-{family}"
                    case = f"{entry}-{protocol}-{family}"
                    check(case + "-allowed", good, mode=mode, destination=(server, "allowed.example"), dns_expected=True)
                    check(case + "-forbidden", good, mode=mode, destination=(server, "blocked.example"),
                          dns_expected=False, deny_kinds=("proxy", "dns", "api"))
        docker("exec", good, "network-policy", "allow", "alias.example")
        check("dns-cache-not-a-grant-after-revocation", good, mode="dns-udp-ip6", destination=("127.0.0.11:53", "allowed.example"),
              dns_expected=False, deny_kinds=("proxy", "dns", "api"))
        docker("exec", good, "network-policy", "deny-all")
        check("no-network-stops-docker-dns", good, mode="dns-udp-ip4", destination=("127.0.0.11:53", "allowed.example"),
              dns_expected=False, deny_kinds=("proxy", "dns", "api"))
        docker("exec", good, "network-policy", "allow", "allowed.example")
        check("dns-restored-needs-fresh-doh", good, mode="dns-udp-ip4", destination=("127.0.0.11:53", "allowed.example"), dns_expected=True)
        clear = start("clear", {"upstream_tls": False, "upstream_port": 18080, "upstream_addr": f"{ip}:18080"})
        check("http-proxy-auth-api", clear, positive=True)
        # Wrong A answers on a reachable route must not change the checked
        # hostname passed to the proxy. No public DNS/CDN address is embedded.
        docker("exec", mock, "touch", "/tmp/pollute")
        polluted = start("polluted")
        check("polluted-a-still-reaches-approved-api", polluted, destination="-", positive=True)
        if not any(e.get("kind") == "dns" and e.get("polluted") for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("polluted DNS positive did not reach its fixture")
        docker("exec", mock, "rm", "/tmp/pollute")
        docker("exec", mock, "touch", "/tmp/pollute6")
        docker("exec", polluted, "network-policy", "allow", "allowed.example")
        check("polluted-aaaa-exact-answer", polluted, mode="dns-udp-ip6",
              destination=("127.0.0.1:1053", "allowed.example"), dns_expected=True)
        if "2001:db8::bad" not in result["checks"][-1]["client"] or not any(
                e.get("type") == 28 and e.get("polluted_aaaa") for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("polluted AAAA answer was not observed at both DNS ends")
        docker("exec", polluted, "network-policy", "allow", "allowed.example")
        check("polluted-aaaa-with-valid-a-api", polluted, destination="-", positive=True)
        docker("exec", polluted, "network-policy", "allow", "allowed.example")
        check("polluted-aaaa-only-no-ipv6-egress", polluted, mode="get-ip6", destination="-", deny_kinds=("api",))
        if result["checks"][-1]["returncode"] == 0 or not any(
                e.get("type") == 28 and e.get("polluted_aaaa") for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("AAAA-only refusal lacked the required polluted resolution")
        check("polluted-aaaa-does-not-grant-forbidden-name", polluted, mode="dns-udp-ip6",
              destination=("127.0.0.1:1053", "blocked.example"), dns_expected=False, deny_kinds=("proxy", "dns", "api"))
        docker("exec", mock, "rm", "/tmp/pollute6")
        for case, overrides, trusted, deny in [
            ("bad-auth", {"auth": {"username": username, "password": "incorrect"}}, True, ("api", "dns")),
            ("bad-proxy-name", {"upstream_host": "wrong-proxy.example"}, True, ("proxy", "api", "dns")),
            ("bad-proxy-ca", {}, False, ("proxy", "api", "dns")),
            ("bad-doh-name", {"doh_url": "https://wrong-resolver.example/dns-query"}, True, ("dns", "api")),
        ]:
            gateway = start(case, overrides, trusted)
            check(case, gateway, destination="-" if case == "bad-doh-name" else None, deny_kinds=deny)
            observed = result["checks"][-1]["upstream_events"]
            if case == "bad-auth" and not any(e.get("kind") == "proxy" and e.get("auth_ok") is False for e in observed):
                raise RuntimeError("wrong-auth negative never reached authentication")
            if case.startswith("bad-proxy") and not any(e.get("kind") == "tcp_accept" and e.get("port") == "18480" for e in observed):
                raise RuntimeError("certificate negative never reached the TLS proxy")
            if case == "bad-doh-name" and not any(e.get("kind") == "tcp_accept" and e.get("port") == "18443" for e in observed):
                raise RuntimeError("DoH certificate negative never reached the TLS origin")
        bad_mock = identity + "-bad-doh-mock"
        bad_settings = json.loads(mock_settings.read_text())
        bad_settings.update(doh_cert="/private/bad.crt", doh_key="/private/bad.key")
        (secret / "bad-mock.json").write_text(json.dumps(bad_settings))
        (secret / "bad-mock.json").chmod(0o600)
        containers.append(bad_mock)
        docker("run", "-d", "--pull", "never", "--name", bad_mock, "--label", label,
               "--network", network, "--cap-drop", "ALL", *mounts, "-v", f"{secret}:/private:ro",
               "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", "/fixture", python, "serve", "/private/bad-mock.json")
        wait_ready(bad_mock)
        bad_ip = json.loads(docker("inspect", bad_mock).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        bad_ca = start("bad-doh-ca", {"upstream_ip": bad_ip, "upstream_addr": f"{bad_ip}:18480"})
        check("bad-doh-ca", bad_ca, destination="-", deny_kinds=("api", "dns"), event_source=bad_mock)
        if not any(e.get("kind") == "tcp_accept" and e.get("port") == "18443" for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("untrusted DoH CA negative never reached the TLS origin")
        docker("exec", good, "network-policy", "allow", "alias.example")
        check("cname-resolution", good, mode="resolve", destination="alias.example", deny_kinds=("api",))
        if '"ok":true' not in result["checks"][-1]["client"]:
            raise RuntimeError("CNAME positive control failed")
        check("cname-is-not-an-api-grant", good, deny_kinds=("api", "proxy"))
        for name in ("nx.example", "redirect.example", "timeout.example"):
            docker("exec", good, "network-policy", "allow", name)
            check(name, good, mode="resolve", destination=name, deny_kinds=("api",))
            observed = result["checks"][-1]["upstream_events"]
            if not any(e.get("kind") == "dns" and e.get("name") == name for e in observed):
                raise RuntimeError("DNS fault did not reach its fixture")
            if any(e.get("target") == "blocked.example:443" for e in observed):
                raise GateFailure("DoH redirect reached a different origin")
            if '"ok":false' not in result["checks"][-1]["client"]:
                raise GateFailure("DNS fault unexpectedly resolved")
        for mode in ("held-h1", "held-h2"):
            docker("exec", good, "network-policy", "allow", "allowed.example")
            held, _ = invoke(good, mode, detached=True)
            wait_ready(held)
            docker("exec", good, "network-policy", "deny-all")
            before = len(events(mock))
            docker("exec", held, "touch", "/tmp/release")
            if docker("wait", held, timeout=15).stdout.strip() != "0":
                raise RuntimeError("held client failed")
            observed = events(mock)[before:]
            if observed:
                raise GateFailure("old TLS/H2 pool reached upstream after revocation")
            result["checks"].append({"case": mode + "-revoked", "passed": True, "upstream_events": observed})

        # Separate processes in one dedicated internal-network container let us
        # kill proxy/DoH independently while a reachable direct API witness stays
        # alive. A client error alone is never the fallback-denial oracle.
        fault_mock = identity + "-fault-mock"
        fault_settings = {**json.loads(mock_settings.read_text()), "events": "/tmp/events.jsonl", "direct_api": True}
        (secret / "fault-mock.json").write_text(json.dumps(fault_settings))
        (secret / "fault-mock.json").chmod(0o600)
        containers.append(fault_mock)
        docker("run", "-d", "--init", "--pull", "never", "--name", fault_mock, "--label", label,
               "--network", network, "--cap-drop", "ALL", *mounts, "-v", f"{secret}:/private:ro",
               "--entrypoint", "sleep", python, "infinity")
        file_event_sources.add(fault_mock)
        docker("exec", fault_mock, "touch", "/tmp/events.jsonl")
        def role_start(role):
            before = len(observe(fault_mock))
            docker("exec", "-d", fault_mock, "/fixture", "serve-"+role, "/private/fault-mock.json")
            for _ in range(30):
                ready = [e for e in observe(fault_mock)[before:] if e.get("kind") == "ready" and e.get("role") == role]
                if ready:
                    return ready[-1]["pid"]
                time.sleep(.1)
            raise RuntimeError("fault fixture role failed startup: "+role)
        def role_kill(role):
            code = """import os,signal,sys,time
from pathlib import Path
role=sys.argv[1];pid=int(Path('/tmp/fixture-'+role+'.pid').read_text())
assert Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\\0')[1]==('serve-'+role).encode()
os.kill(pid,signal.SIGKILL)
for _ in range(100):
 p=Path(f'/proc/{pid}/stat')
 if not p.exists() or p.read_text().split()[2]=='Z': break
 time.sleep(.02)
else: raise RuntimeError('fixture process did not exit')
print(pid)
"""
            return int(docker("exec", fault_mock, "python", "-c", code, role).stdout)
        pids = {role: role_start(role) for role in ("api", "doh", "proxy")}
        fault_ip = json.loads(docker("inspect", fault_mock).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        witness = identity + "-direct-witness"
        containers.append(witness)
        docker("run", "-d", "--pull", "never", "--name", witness, "--label", label, "--network", network,
               "--cap-drop", "ALL", *mounts, "--entrypoint", "sleep", python, "infinity")
        def direct_control(case):
            before = len(observe(fault_mock))
            response = docker("exec", witness, "/fixture", "get-fallback", fault_ip, "/public/ca.crt", check=False)
            received = observe(fault_mock)[before:]
            if response.returncode or not any(e.get("kind") == "api-direct" for e in received):
                raise RuntimeError("direct fallback witness is not reachable")
            result["checks"].append({"case": case, "passed": True, "upstream_events": received})
        direct_control("fallback-witness-positive")
        fault = start("fault", {"upstream_ip": fault_ip, "upstream_addr": f"{fault_ip}:18480"})
        check("proxy-process-before-kill", fault, mode="get-fallback", destination=fault_ip, positive=True,
              deny_kinds=("api-direct",), event_source=fault_mock)
        if role_kill("proxy") != pids["proxy"]:
            raise RuntimeError("proxy PID changed unexpectedly")
        check("proxy-sigkill-no-direct-fallback", fault, mode="get-fallback", destination=fault_ip,
              deny_kinds=("api", "api-direct", "dns", "proxy"), event_source=fault_mock)
        direct_control("fallback-witness-alive-during-proxy-death")
        docker("exec", fault, "network-policy", "deny-all")
        new_pid = role_start("proxy")
        if new_pid == pids["proxy"]:
            raise RuntimeError("proxy restart did not establish a new process")
        result.setdefault("process_faults", []).append({"role": "proxy", "signal": "SIGKILL", "old_pid": pids["proxy"], "new_pid": new_pid})
        check("proxy-restart-cannot-undo-deny-all", fault, mode="get-fallback", destination=fault_ip,
              deny_kinds=("api", "api-direct", "proxy"), event_source=fault_mock)
        docker("exec", fault, "network-policy", "allow", "nx.example")
        check("proxy-restart-cannot-restore-old-host", fault, mode="get-fallback", destination=fault_ip,
              deny_kinds=("api", "api-direct", "proxy"), event_source=fault_mock)
        docker("exec", fault, "network-policy", "allow", "allowed.example")
        check("proxy-restored-explicit-current-grant", fault, mode="get-fallback", destination="-", positive=True,
              deny_kinds=("api-direct",), event_source=fault_mock)
        if role_kill("doh") != pids["doh"]:
            raise RuntimeError("DoH PID changed unexpectedly")
        docker("exec", fault, "network-policy", "allow", "allowed.example")
        check("resolver-sigkill-no-fallback", fault, mode="dns-udp-ip4", destination=("127.0.0.1:1053", "allowed.example"),
              dns_expected=False, deny_kinds=("api", "api-direct", "dns"), event_source=fault_mock)
        if not any(e.get("target") == "resolver.example:443" for e in result["checks"][-1]["upstream_events"]):
            raise RuntimeError("failed DNS request never reached its live proxy")
        if any(e.get("kind") == "proxy" and e.get("target") != "resolver.example:443"
               for e in result["checks"][-1]["upstream_events"]):
            raise GateFailure("resolver failure attempted a different upstream target")
        check("resolver-dead-proxy-api-still-live", fault, mode="get-fallback", destination=fault_ip, positive=True,
              deny_kinds=("api-direct",), event_source=fault_mock)
        docker("exec", fault, "network-policy", "deny-all")
        new_pid = role_start("doh")
        if new_pid == pids["doh"]:
            raise RuntimeError("DoH restart did not establish a new process")
        result["process_faults"].append({"role": "doh", "signal": "SIGKILL", "old_pid": pids["doh"], "new_pid": new_pid})
        check("resolver-restart-cannot-undo-deny-all", fault, mode="dns-udp-ip4", destination=("127.0.0.1:1053", "allowed.example"),
              dns_expected=False, deny_kinds=("proxy", "dns", "api", "api-direct"), event_source=fault_mock)
        docker("exec", fault, "network-policy", "allow", "nx.example")
        check("resolver-restart-cannot-restore-old-host", fault, mode="dns-udp-ip4", destination=("127.0.0.1:1053", "allowed.example"),
              dns_expected=False, deny_kinds=("proxy", "dns", "api", "api-direct"), event_source=fault_mock)
        docker("exec", fault, "network-policy", "allow", "allowed.example")
        check("resolver-restored-explicit-current-grant", fault, mode="get-fallback", destination="-", positive=True,
              deny_kinds=("api-direct",), event_source=fault_mock)
        (output / "fault-events.json").write_text(json.dumps(observe(fault_mock), indent=2)+"\n")
        result["status"] = "passed"
    except GateFailure as error:
        result.update(status="security_gate_failed", error=str(error))
    except Exception as error:
        result["error"] = str(error)
    finally:
        cleanup = []
        for name in reversed(containers):
            inspected = docker("container", "inspect", name, check=False)
            if inspected.returncode:
                continue
            info = json.loads(inspected.stdout)[0]
            if info["Config"].get("Labels", {}).get("searchswe.transport") != identity:
                cleanup.append("container ownership mismatch")
                continue
            logs = docker("logs", name, check=False)
            evidence = logs.stdout + logs.stderr
            if any(needle in inspected.stdout + evidence for needle in needles):
                result["status"] = "security_gate_failed"
                result["error"] = "credential canary in container metadata/logs (withheld)"
            else:
                (output / (name.removeprefix(identity + "-") + ".log")).write_text(evidence)
            if docker("rm", "-f", name, check=False).returncode:
                cleanup.append("container cleanup failed")
        for name in networks:
            info = json.loads(docker("network", "inspect", name).stdout)[0]
            if info["Labels"].get("searchswe.transport") != identity or info.get("Containers"):
                cleanup.append("network ownership/membership mismatch")
            elif docker("network", "rm", name, check=False).returncode:
                cleanup.append("network cleanup failed")
        if created_image:
            info = json.loads(docker("image", "inspect", image_tag).stdout)[0]
            if info["Config"]["Labels"].get("searchswe.transport") != identity:
                cleanup.append("image ownership mismatch")
            elif docker("image", "rm", image_tag, check=False).returncode:
                cleanup.append("image cleanup failed")
        private.cleanup()
        result["cleanup_errors"] = cleanup
        if cleanup:
            result["status"] = "cleanup_error"
        serialized = json.dumps(result, indent=2)
        if any(needle in serialized for needle in needles):
            serialized = json.dumps({"status": "security_gate_failed", "error": "credential canary in result (withheld)"})
            result["status"] = "security_gate_failed"
        (output / "result.json").write_text(serialized + "\n")
        print(json.dumps({"status": result["status"], "error": result.get("error"), "output": str(output)}))
    return 0 if result["status"] == "passed" else 1 if result["status"] == "security_gate_failed" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--python-image", default="python:3.13-slim")
    parser.add_argument("--go", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    raise SystemExit(run(parser.parse_args()))
