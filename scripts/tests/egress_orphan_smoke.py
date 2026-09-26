"""Kill one dedicated host driver, then verify its lease and orphan recovery."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.egress.ownership import owner_root, read_manifest
from scripts.egress_cleanup import recover, inventory
from scripts.tests.egress_credentials import CredentialProbe
from environments.egress.gateway import LEASE_SECONDS


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "infrastructure_error", "checks": []}
    private, child = None, None
    credentials = CredentialProbe() if args.credential_probe else None
    try:
        with (output / "driver.log").open("w") as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).with_name("egress_adapter_smoke.py")),
                                      "--gateway-image", args.gateway_image, "--output", str(output / "child"),
                                      "--orphan-child", *(["--auth-file", str(credentials.path)] if credentials else [])],
                                      stdout=log, stderr=subprocess.STDOUT)
            ready = output / "child/owner-ready.json"
            deadline = time.monotonic() + 180
            while not ready.exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("orphan driver failed startup")
                time.sleep(.2)
            owner = json.loads(ready.read_text())
            private = Path(owner["private"])
            if credentials:
                if not owner.get("credential_boundary_checked"):
                    raise RuntimeError("child credential boundary probe did not run")
                result["checks"].append({"case": "pre-crash-credential-boundary", "passed": True})
            try:
                recover(private, remove=False)
            except BlockingIOError:
                result["checks"].append({"case": "live-owner-excluded", "passed": True})
            else:
                raise RuntimeError("live owner lock was not enforced")
            child.kill()
            child.wait(timeout=15)
        result["driver_returncode"] = child.returncode
        manifest = read_manifest(private)
        resources = inventory(manifest)
        gateway = next(r["id"] for r in resources if r["gateway"])
        # A single bounded lease deadline, not polling for an external wake.
        time.sleep(LEASE_SECONDS + 1)
        closed = subprocess.run(["docker", "exec", gateway, "network-policy", "show"],
                                capture_output=True, text=True, timeout=15)
        state = json.loads(closed.stdout)
        if closed.returncode == 0 or state.get("ready") or state.get("error") != "lease_expired":
            raise RuntimeError("host death did not expire the gateway lease")
        result["checks"].append({"case": "host-sigkill-lease-expired", "passed": True})
        recovered = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "egress_cleanup.py"),
                                    "--directory", str(private), "--remove"],
                                   check=True, capture_output=True, text=True, timeout=180)
        result["recovery"] = json.loads(recovered.stdout)
        audits = result["recovery"]["audit_paths"]
        if len(audits) != 1:
            raise RuntimeError("orphan recovery did not preserve one gateway audit")
        audit = Path(audits[0])
        info = audit.lstat()
        if (audit.parent != owner_root() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or info.st_nlink != 1):
            raise RuntimeError("unsafe recovery audit permissions")
        data = audit.read_bytes()
        if credentials:
            credentials.scan(data, "recovered-audit")
        # entrypoint.sh emits one fixed readiness banner in addition to JSON
        # controller events. Do not silently accept any other unstructured log.
        records = [json.loads(line) for line in data.splitlines()
                   if line and line != b"Search-SWE restricted gateway ready"]
        if not records or any(row.get("instance") != owner["instance"] for row in records):
            raise RuntimeError("recovered audit lost instance ownership")
        if not {"generation_ready", "lease_expired"} <= {row["event"] for row in records}:
            raise RuntimeError("recovered audit lost policy/expiry events")
        ready = [row for row in records if row["event"] == "generation_ready"]
        if any(not row.get("generation") or len(row.get("policy_sha256", "")) != 64 for row in ready):
            raise RuntimeError("recovered audit lost policy generation/hash")
        if not any(isinstance(row.get("packet_counters"), dict) and "proxy_packets" in row["packet_counters"] for row in ready):
            raise RuntimeError("recovered audit lost kernel packet counters")
        shutil.copyfile(audit, output / "recovery-audit.log")
        result["checks"].append({"case": "durable-owner-only-policy-audit", "passed": True,
                                 "sha256": hashlib.sha256(data).hexdigest(), "events": len(records)})
        if private.exists() or inventory(manifest):
            raise RuntimeError("orphan resources/private directory remain")
        result["checks"].append({"case": "owned-orphan-removed", "passed": True})
        result["status"] = "passed"
    except Exception as error:
        result["error"] = str(error)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=15)
        if private is None:
            identity_file = output / "child/driver-identity.json"
            if identity_file.exists():
                instance = json.loads(identity_file.read_text())["instance"]
                candidates = list(owner_root().glob("instance-" + instance + "-*"))
                if len(candidates) == 1:
                    private = candidates[0]
        if private is not None and private.exists():
            try:
                result["failure_recovery"] = recover(private, remove=True)
            except Exception as error:
                result["cleanup_error"] = str(error)
        if credentials:
            try:
                credentials.artifacts(output)
                credentials.scan(json.dumps(result), "orphan-result")
                credentials.close()
                if credentials.path.exists():
                    raise RuntimeError("credential source was not removed")
                result["checks"].append({"case": "orphan-credential-artifacts-clean", "passed": True})
            except Exception:
                result = {"status": "credential_evidence_error", "error": "Orphan credential evidence validation failed"}
            finally:
                credentials.close()
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--credential-probe", action="store_true", help="Also test synthetic credentials across host death and recovery")
    raise SystemExit(run(parser.parse_args()))
