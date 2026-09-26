"""Synthetic credential probes. Never print or persist the canary in evidence."""

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from urllib.parse import quote
import uuid

from scripts.egress.config import read_auth
from scripts.egress.ownership import owner_root


class CredentialLeak(RuntimeError):
    pass


class CredentialProbe:
    def __init__(self, auth_file=None):
        self.owned = None
        if auth_file is None:
            self.owned = tempfile.TemporaryDirectory(prefix="credential-probe-", dir=owner_root())
            auth_file = Path(self.owned.name) / "auth.json"
            auth = {"username": "swe_user_" + uuid.uuid4().hex,
                    "password": "swe_password_" + uuid.uuid4().hex + '/+=\\"ü'}
            with os.fdopen(os.open(auth_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                json.dump(auth, stream)
        self.path = Path(auth_file).absolute()
        self.auth = read_auth(self.path)
        self.patterns = {base64.b64encode((self.auth["username"] + ":" + self.auth["password"]).encode())}
        for value in self.auth.values():
            self.patterns.update(v.encode() for v in (value, quote(value, safe=""), json.dumps(value)[1:-1]))
        # A scanner that never matches must not pass the isolation gate.
        for value in self.patterns:
            try:
                self.scan(b"prefix " + value + b" suffix", "scanner-positive-control")
            except CredentialLeak:
                continue
            raise RuntimeError("credential scanner positive control failed")

    def scan(self, data, surface):
        data = data.encode() if isinstance(data, str) else data
        if any(pattern in data for pattern in self.patterns):
            raise CredentialLeak("Synthetic credential exposed on " + surface)

    def artifacts(self, output):
        found = []
        for path in sorted(Path(output).rglob("*")):
            if path.is_symlink():
                raise RuntimeError("unexpected symlink in credential evidence")
            if path.is_file():
                try:
                    self.scan(path.read_bytes(), "output-artifact")
                except CredentialLeak:
                    # Keep the filename/failure, not the credential-bearing data.
                    path.write_text("Withheld: synthetic credential canary detected.\n")
                    found.append(str(path.relative_to(output)))
        if found:
            raise CredentialLeak("Synthetic credential artifacts withheld: " + ", ".join(found))

    async def environment(self, environment, *, worker=False):
        """Inspect real services without supplying expected secrets to them."""
        private = Path(environment._private.name)
        loaded = json.loads((private / "input.json").read_text()).get("auth")
        if loaded != self.auth:
            raise RuntimeError("private credential positive control failed")
        self.scan(repr(environment.egress), "public-config-repr")
        rendered = await environment._run_docker_compose_command(["config", "--format", "json"])
        self.scan(rendered.stdout, "merged-compose")
        services = json.loads(rendered.stdout)["services"]
        service_gateway = "harbor-docker-egress-control-sidecar"
        paths = [str(self.path), str(private / "input.json"),
                 "/opt/searchswe/input.json", "/run/searchswe/gost.json", "/run/searchswe/control.sock"]
        script = """import base64,json,os
from pathlib import Path
data=[json.dumps(dict(os.environ)).encode()]
count=0
for process in Path('/proc').iterdir():
 if not process.name.isdigit(): continue
 for field in ('cmdline','environ'):
  try: data.append((process/field).read_bytes());count+=1
  except (FileNotFoundError,PermissionError,ProcessLookupError): pass
print(json.dumps({'data':[base64.b64encode(v).decode() for v in data],
 'process_fields':count,'positive_file':Path('/etc/os-release').is_file(),
 'private_visible':any(Path(p).exists() or (Path('/proc/1/root')/p.lstrip('/')).exists() for p in PRIVATE_PATHS)}))
"""
        task_services = []
        for service in services:
            # The gateway's PRIVATE files legitimately contain credentials;
            # its environment and process argv must still not contain them.
            checked_paths = [] if service == service_gateway else paths
            code = "PRIVATE_PATHS=" + repr(checked_paths) + "\n" + script
            response = await environment.service_exec("python3 -c " + shlex.quote(code), service=service)
            if response.return_code:
                raise RuntimeError("credential process probe failed")
            report = json.loads(response.stdout)
            if not report["positive_file"] or not report["process_fields"] or report["private_visible"]:
                raise RuntimeError("private-files/process-visibility probe failed")
            for blob in report["data"]:
                self.scan(base64.b64decode(blob), "service-environment-or-argv")
            if service != service_gateway:
                task_services.append(service)
        ids = await asyncio.to_thread(subprocess.run,
            ["docker", "ps", "-aq", "--filter", f"label=searchswe.egress.instance={environment._instance}"],
            capture_output=True, text=True, check=True, timeout=30)
        if not ids.stdout.split():
            raise RuntimeError("container metadata positive control failed")
        metadata = await asyncio.to_thread(subprocess.run, ["docker", "inspect", *ids.stdout.split()],
                                           capture_output=True, text=True, check=True, timeout=30)
        self.scan(metadata.stdout, "container-metadata")
        if worker:
            code = """import hashlib,json
from pathlib import Path
config=json.loads(Path('/run/searchswe/gost.json').read_text())
auth=config['chains'][0]['hops'][0]['nodes'][0]['connector']['auth']
print(hashlib.sha256(json.dumps(auth,sort_keys=True).encode()).hexdigest())
"""
            loaded = await environment.service_exec("python3 -c " + shlex.quote(code), service=service_gateway)
            expected = hashlib.sha256(json.dumps(self.auth, sort_keys=True).encode()).hexdigest()
            if loaded.return_code or loaded.stdout.strip() != expected:
                raise RuntimeError("live worker credential positive control failed")
        logs = await environment._run_docker_compose_command(["logs", "--no-color"])
        self.scan((logs.stdout or "") + (logs.stderr or ""), "container-logs")
        return {"case": "synthetic-credential-boundary", "passed": True,
                "instance": environment._instance, "task_services": sorted(task_services),
                "worker_config_checked": worker}

    def close(self):
        if self.owned is not None:
            self.owned.cleanup()
