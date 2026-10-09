"""Phase-scoped direct/proxy Docker extension; never patches installed Harbor."""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import time
import uuid

import yaml
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.docker.docker import DockerEnvironment, _sanitize_docker_compose_project_name
from harbor.models.task.config import NetworkMode, TaskOS

from scripts.egress.compose import SERVICE, declared_services, validate_final
from scripts.egress.config import DEFAULT_IMAGE, direct_config, exact_hosts, load_config, require_supported_harbor
from scripts.egress.ownership import ProjectLock, PrivateDirectory, owner_root
from environments.egress.gateway import LEASE_SECONDS


def docker_json(*arguments, timeout=15):
    response = subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True, timeout=timeout)
    return json.loads(response.stdout)


def gateway_image_info(reference):
    try:
        return docker_json("image", "inspect", reference)[0]
    except subprocess.CalledProcessError as error:
        # Only a missing image permits a pull; daemon/permission errors must
        # retain their original cause rather than becoming registry requests.
        if "no such image:" not in (error.stderr or "").lower():
            raise
    logging.getLogger(__name__).info("Pulling missing egress gateway image %s", reference)
    try:
        subprocess.run(["docker", "pull", "--platform", "linux/amd64", reference],
                       check=True, capture_output=True, text=True, timeout=300)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            f"Could not pull egress gateway image {reference}; check Docker registry "
            "access/authentication and the Docker daemon's proxy settings, or preload "
            "the image with docker pull. Task EGRESS_CONFIG does not configure image downloads."
        ) from error
    return docker_json("image", "inspect", reference)[0]


class PhaseScopedDocker(DockerEnvironment):
    """Linux/rootful/local, exact-host, phase-scoped direct or proxy egress."""

    def __init__(self, *args, egress_config: str | None = None, egress_image: str = DEFAULT_IMAGE,
                 egress_dns: str | None = None, **kwargs):
        require_supported_harbor()
        if egress_config is not None and (egress_dns is not None or egress_image != DEFAULT_IMAGE):
            raise ValueError("egress_config cannot be combined with egress_image/egress_dns overrides")
        self.egress = (load_config(egress_config) if egress_config is not None else
                       direct_config(egress_image, egress_dns.split(",") if egress_dns is not None else None))
        self._private = None
        self._gateway_overlay = None
        self._gateway_image = None
        self._engine_paths = ()
        self._policy_lock = asyncio.Lock()
        self._heartbeat = None
        self._heartbeat_error = None
        self._starting = True
        self._instance = uuid.uuid4().hex
        self._owner_lock = None
        self._compose_started = False
        self._rendered_document = None
        self._daemon_id = None
        super().__init__(*args, **kwargs)
        if self.os != TaskOS.LINUX or not self._enable_egress_control or self._keep_containers:
            raise ValueError("Restricted egress requires Linux isolation and does not support keep_containers")
        for policy in (self.network_policy, *self._phase_network_policies):
            self._check_policy(policy)

    @staticmethod
    def _requires_egress_control(*, startup_network_policy, phase_network_policies):
        # Explicit selection also supports a direct public phase. Keep the
        # controller present so a later restriction never needs a new namespace.
        return True

    @staticmethod
    def _egress_control_kernel_support():
        # The trusted controller executes real nft transactions before becoming
        # healthy; no main service may start before that. Avoid Harbor's separate
        # probe image/pull, but never bypass the actual kernel enforcement gate.
        return True

    @property
    def capabilities(self):
        return EnvironmentCapabilities(disable_internet=True, network_allowlist=True,
                                       network_allowlist_hostnames=True, dynamic_network_policy=True,
                                       mounted=True, docker_compose=True)

    def _check_policy(self, policy):
        if (policy.network_mode == NetworkMode.PUBLIC
                and self.egress.settings.get("transport") == "direct"):
            return
        if policy.network_mode not in (NetworkMode.ALLOWLIST, NetworkMode.NO_NETWORK):
            raise ValueError("Restricted egress does not support any public phase")
        exact_hosts(policy.allowed_hosts)
        if self.egress.settings.get("upstream_host") in policy.allowed_hosts:
            raise ValueError("An upstream proxy cannot also be an allowed task/API destination")
        if policy.network_mode == NetworkMode.NO_NETWORK and policy.allowed_hosts:
            raise ValueError("no-network policy cannot include allowed_hosts")

    def _preflight_gateway(self):
        if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
            raise ValueError("Restricted egress currently supports local Linux amd64 only")
        context = docker_json("context", "inspect")[0]
        endpoint = (None if os.environ.get("DOCKER_CONTEXT") else os.environ.get("DOCKER_HOST")) or context["Endpoints"]["docker"]["Host"]
        if not endpoint.startswith("unix://"):
            raise ValueError("Restricted egress requires a local Unix-socket Docker daemon")
        info = docker_json("info", "--format", "{{json .}}")
        security = " ".join(info.get("SecurityOptions", []))
        if (info.get("OSType") != "linux" or "rootless" in security or "userns" in security
                or "desktop" in info.get("OperatingSystem", "").lower()):
            raise ValueError("Restricted egress requires native Linux rootful Docker without userns remapping")
        if info.get("Architecture") not in {"x86_64", "amd64"} or info.get("KernelVersion") != platform.release():
            raise ValueError("Host and Docker daemon must share the same native Linux amd64 kernel")
        if not isinstance(info.get("ID"), str) or not info["ID"]:
            raise ValueError("Docker daemon identity is unavailable")
        self._daemon_id = info["ID"]
        self._engine_paths = (endpoint.removeprefix("unix://"), info["DockerRootDir"])
        project = _sanitize_docker_compose_project_name(self.session_id)
        self._owner_lock = ProjectLock(project)
        existing = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
                                  check=True, capture_output=True, text=True, timeout=15)
        if existing.stdout.strip():
            raise ValueError("Existing Compose project; recover its owned orphan before starting a new instance")
        for resource in ("network", "volume"):
            existing = subprocess.run(["docker", resource, "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                                      check=True, capture_output=True, text=True, timeout=15)
            if existing.stdout.strip():
                raise ValueError("Existing Compose resources; recover the owned orphan before starting")
        self._engine_paths = (*self._engine_paths, str(owner_root()))
        image = gateway_image_info(self.egress.image)
        labels = image["Config"].get("Labels", {})
        if (image.get("Os") != "linux" or image.get("Architecture") != "amd64"
                or labels.get("org.search-swe.egress.gateway") != "1"
                or labels.get("org.search-swe.egress.component") != "gost-x-0.10.9-searchswe-1"):
            raise ValueError("Expected a supported Search-SWE gateway image (linux/amd64)")
        sources = Path(__file__).resolve().parents[1] / "environments/egress"
        gateway_sha = hashlib.sha256((sources / "gateway.py").read_bytes()).hexdigest()
        patch_sha = hashlib.sha256((sources / "patch_gost.py").read_bytes()).hexdigest()
        runtime_sha = hashlib.sha256((sources / "runtime.lock.json").read_bytes()).hexdigest()
        if (labels.get("org.search-swe.egress.source-sha256") != gateway_sha
                or labels.get("org.search-swe.egress.patch-sha256") != patch_sha
                or labels.get("org.search-swe.egress.runtime-lock-sha256") != runtime_sha):
            raise ValueError("Gateway image is stale or unverified; rebuild it from this checkout")
        # Verify contents as well as labels. This unprivileged, networkless
        # preflight has no configuration/credential mounts, and is always removed.
        name = "searchswe-egress-preflight-" + uuid.uuid4().hex[:12]
        script = """import hashlib,json
from pathlib import Path
m=json.loads(Path('/usr/share/searchswe-egress/component.json').read_text())
assert hashlib.sha256(Path('/bin/gost').read_bytes()).hexdigest()==m['binary_sha256']
runtime=Path('/usr/share/searchswe-egress/runtime.json').read_bytes()
lock=json.loads(runtime)
records=[dict(line.split(':',1) for line in record.splitlines() if ':' in line)
         for record in Path('/lib/apk/db/installed').read_text().split('\\n\\n')]
assert {v['P']:v['V'] for v in records if 'P' in v}==lock['installed']
assert Path('/etc/alpine-release').read_text().strip()==lock['alpine_release']
print(json.dumps({'gateway':hashlib.sha256(Path('/opt/searchswe/gateway.py').read_bytes()).hexdigest(),
                 'patch':m['patch_sha256'],'runtime':hashlib.sha256(runtime).hexdigest()}))
"""
        try:
            contents = docker_json("run", "--pull", "never", "--name", name,
                                   "--label", f"searchswe.preflight={name}", "--network", "none", "--read-only",
                                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                                   "--memory", "256m", "--cpus", "1", "--entrypoint", "python3", image["Id"], "-c", script,
                                   timeout=60)
            if contents != {"gateway": gateway_sha, "patch": patch_sha, "runtime": runtime_sha}:
                raise ValueError("Gateway image contents do not match this checkout")
        finally:
            inspected = subprocess.run(["docker", "container", "inspect", name], capture_output=True, text=True, timeout=15)
            if inspected.returncode and "No such" not in inspected.stderr:
                raise RuntimeError("Could not verify gateway preflight cleanup")
            if inspected.returncode == 0:
                owned = json.loads(inspected.stdout)[0]["Config"].get("Labels", {})
                if owned.get("searchswe.preflight") != name:
                    raise RuntimeError("Gateway preflight container ownership mismatch")
                # This probe has no network, capabilities or secrets. Allow a
                # bounded slow containerd teardown; this is not an egress lease.
                removed = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
                if removed.returncode:
                    remains = subprocess.run(["docker", "container", "inspect", name], capture_output=True, text=True, timeout=15)
                    if remains.returncode == 0 or "No such" not in remains.stderr:
                        raise RuntimeError("Gateway preflight container cleanup failed")
        self._gateway_image = image["Id"]

    def _declared_services(self):
        paths = list(self.extra_docker_compose_paths)
        if self._environment_docker_compose_path.exists():
            paths.insert(0, self._environment_docker_compose_path)
        return declared_services([yaml.safe_load(path.read_text()) for path in paths])

    @property
    def _docker_compose_paths(self):
        paths = super()._docker_compose_paths
        return [*paths, self._gateway_overlay] if self._gateway_overlay else paths

    async def _ensure_egress_control_sidecar_image_built(self):
        # Immutable ID is resolved from the validated image; never rebuild
        # Harbor's original, unpatched sidecar or fall back to it.
        self._env_vars.egress_control_sidecar_image_name = self._gateway_image

    def _prepare_private_overlay(self):
        names = self._declared_services()
        settings = self.egress.private_settings()
        self._private = PrivateDirectory(self._instance, _sanitize_docker_compose_project_name(self.session_id), self._gateway_image,
                                         daemon_id=self._daemon_id)
        root = Path(self._private.name)
        root.chmod(0o700)
        config = root / "input.json"
        with os.fdopen(os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(settings, stream)
        services = {name: {"cap_drop": ["NET_RAW", "NET_ADMIN"],
                           "security_opt": ["no-new-privileges:true"],
                           "labels": {"searchswe.egress.instance": self._instance}} for name in names}
        services[SERVICE] = {
            "cap_drop": ["ALL"], "cap_add": ["NET_ADMIN", "NET_RAW", "DAC_OVERRIDE"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,
            "labels": {"searchswe.egress.instance": self._instance},
            # Late Docker creates may bootstrap only a closed namespace. The
            # host applies Harbor's real baseline before starting task services.
            "environment": {"SEARCHSWE_EGRESS_INSTANCE": self._instance,
                            "EGRESS_CONTROL_INITIAL_NETWORK_MODE": "no-network",
                            "EGRESS_CONTROL_INITIAL_ALLOWED_HOSTS": ""},
            "tmpfs": ["/run/searchswe:mode=0700", "/tmp:mode=1777"],
            "sysctls": {"net.ipv6.conf.all.disable_ipv6": "1", "net.ipv6.conf.default.disable_ipv6": "1"},
            "volumes": [{"type": "bind", "source": str(config), "target": "/opt/searchswe/input.json", "read_only": True}],
        }
        self._gateway_overlay = root / "compose.json"
        self._gateway_overlay.write_text(json.dumps({"services": services, "networks": {
            "default": {"labels": {"searchswe.egress.instance": self._instance}}}}))
        self._gateway_overlay.chmod(0o600)

    async def _run_docker_compose_command(self, command, *args, **kwargs):
        if command and command[0] in {"up", "build"}:
            rendered = await super()._run_docker_compose_command(["config", "--format", "json"], timeout_sec=30)
            document = json.loads(rendered.stdout)
            if any(v.get("labels", {}).get("searchswe.egress.instance") != self._instance for v in document.get("volumes", {}).values()):
                overlay = json.loads(self._gateway_overlay.read_text())
                overlay["volumes"] = {name: {"labels": {"searchswe.egress.instance": self._instance}}
                                      for name in document["volumes"]}
                self._gateway_overlay.write_text(json.dumps(overlay))
                rendered = await super()._run_docker_compose_command(["config", "--format", "json"], timeout_sec=30)
            protected = [self.trial_paths.trial_dir / "egress"]
            if self.egress.path is not None:
                protected.append(self.egress.path)
            if self.egress.auth_path is not None:
                protected.append(self.egress.auth_path)
            document = json.loads(rendered.stdout)
            validate_final(document, private_directory=self._private.name,
                           image=self._gateway_image, engine_paths=self._engine_paths, protected_paths=protected)
            await asyncio.to_thread(self._check_resource_ownership, document)
            self._rendered_document = document
            if command[0] == "up" and self._heartbeat is None:
                self._heartbeat = asyncio.create_task(self._keep_lease())
            if command[0] == "up":
                self._compose_started = True
                # Docker create may be slow, but cannot be allowed to mint a
                # fresh permissive lease after cancellation. Bootstrap ONLY the
                # trusted service in no-network; authorize with a deadline once
                # its controller is alive, before any task entrypoint can run.
                await super()._run_docker_compose_command(
                    ["up", "--detach", "--wait", "--no-deps", SERVICE], *args, **kwargs)
                await self.set_network_policy(self.network_policy)
        return await super()._run_docker_compose_command(command, *args, **kwargs)

    def _check_resource_ownership(self, document):
        """Compose must never adopt/delete an existing foreign named resource."""
        if docker_json("info", "--format", "{{json .ID}}") != self._daemon_id:
            raise ValueError("Docker daemon identity changed; preserve the instance for recovery")
        project = document["name"]
        def check_labels(labels):
            if (labels.get("searchswe.egress.instance") != self._instance
                    or labels.get("com.docker.compose.project") != project):
                raise ValueError("Existing Compose resource is not owned by this egress instance")
        for kind, entries in (("volume", document.get("volumes", {})), ("network", document.get("networks", {}))):
            for resource in entries.values():
                name = resource["name"]
                inspected = subprocess.run(["docker", kind, "inspect", name], capture_output=True, text=True, timeout=15)
                if inspected.returncode:
                    error = inspected.stderr.lower()
                    if (f"no such {kind}:" in error or f"{kind} {name} not found" in error
                            or f"get {name}: no such volume" in error):
                        continue
                    raise RuntimeError("Cannot verify Compose resource ownership")
                info = json.loads(inspected.stdout)[0]
                check_labels(info.get("Labels") or {})
                if kind == "network":
                    for identity in info.get("Containers", {}):
                        check_labels(docker_json("container", "inspect", identity)[0]["Config"].get("Labels") or {})
        containers = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
                                    capture_output=True, text=True, check=True, timeout=15).stdout.split()
        for identity in containers:
            check_labels(docker_json("container", "inspect", identity)[0]["Config"].get("Labels") or {})

    @staticmethod
    def _deadline():
        return time.monotonic_ns() + LEASE_SECONDS * 10**9

    async def _require_daemon(self):
        identity = await asyncio.to_thread(docker_json, "info", "--format", "{{json .ID}}", timeout=8)
        if identity != self._daemon_id:
            raise RuntimeError("Docker daemon identity changed; original instance requires recovery")

    async def _renew_lease(self):
        await self._require_daemon()
        result = await self._run_docker_compose_command(
            ["exec", "--no-TTY", SERVICE, "network-policy", "--deadline-ns", str(self._deadline()), "lease"],
            timeout_sec=8)
        if not json.loads(result.stdout).get("ready"):
            raise RuntimeError("Gateway lease was not acknowledged")

    async def _keep_lease(self):
        while True:
            try:
                async with self._policy_lock:
                    await self._renew_lease()
            except asyncio.CancelledError:
                raise
            except Exception:
                if not self._starting:
                    self._heartbeat_error = RuntimeError("Gateway control lease failed; environment must stop")
                    return
                # Only during startup, before Docker has created the service.
            await asyncio.sleep(1 if self._starting else 5)

    async def _stop_heartbeat(self):
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            try:
                await self._heartbeat
            except asyncio.CancelledError:
                pass
            self._heartbeat = None

    @staticmethod
    async def _collect_buffered_output(process, **kwargs):
        try:
            return await DockerEnvironment._collect_buffered_output(process, **kwargs)
        except asyncio.CancelledError:
            await DockerEnvironment._terminate_process(process)
            raise

    async def _force_closed(self):
        await self._stop_heartbeat()
        self._heartbeat_error = RuntimeError("Gateway control failed or stopped; create a new environment")
        try:
            await self._require_daemon()
        except Exception:
            # Never send a deny/kill to another daemon's similarly named
            # Compose service. Fence the original through its bounded lease.
            await asyncio.sleep(LEASE_SECONDS + 1)
            raise RuntimeError("Original Docker daemon unavailable; lease expired, cleanup unverified") from None
        try:
            await self._run_docker_compose_command(
                ["exec", "--no-TTY", SERVICE, "network-policy", "deny-all"], timeout_sec=75)
        except Exception:
            pass
        # Even a successful deny-all cannot fence a delayed Docker exec from a
        # cancelled setter: terminating the CLI does not terminate its remote
        # exec. Kill the container (including every pending exec) before return.
        # Failure is terminal; a later trial must create a new environment.
        try:
            await self._run_docker_compose_command(["kill", SERVICE], timeout_sec=30)
        except Exception:
            # No further renewals. Already-issued requests retain their original
            # deadlines and the kernel expires even with a paused controller.
            await asyncio.sleep(LEASE_SECONDS + 1)
            raise RuntimeError("Docker control unavailable; lease expired, cleanup remains unverified") from None

    async def set_network_policy(self, policy):
        async with self._policy_lock:
            try:
                if policy == self.network_policy:
                    # Reapplying the same effective policy must also recover a
                    # crashed/closed worker rather than trust a cached value.
                    self.validate_network_policy_support(policy)
                    await self._apply_network_policy(policy)
                else:
                    await super().set_network_policy(policy)
            except BaseException:
                cleanup = asyncio.create_task(self._force_closed())
                # Cancellation is not permission to leave an in-flight policy
                # replacement running after the environment reports failure.
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
                raise

    async def _apply_network_policy(self, policy):
        if self._heartbeat_error is not None:
            raise self._heartbeat_error
        await self._require_daemon()
        self._check_policy(policy)
        arguments = ({NetworkMode.NO_NETWORK: ["deny-all"], NetworkMode.PUBLIC: ["allow-all"]}
                     .get(policy.network_mode, ["allow", *policy.allowed_hosts]))
        response = await self._run_docker_compose_command(
            ["exec", "--no-TTY", SERVICE, "network-policy", "--deadline-ns", str(self._deadline()), *arguments], timeout_sec=75)
        state = json.loads(response.stdout)
        if (not state.get("ready") or state.get("mode") != policy.network_mode.value
                or state.get("hosts") != exact_hosts(policy.allowed_hosts)):
            raise RuntimeError("Gateway did not acknowledge the requested phase policy")

    async def start(self, force_build):
        preflight = asyncio.create_task(asyncio.to_thread(self._preflight_gateway))
        try:
            await asyncio.shield(preflight)
            self._prepare_private_overlay()
            await super().start(force_build)
            await self._renew_lease()
            self._starting = False
        except BaseException:
            # A cancelled to_thread must not create a late probe/lock after the
            # caller believes cleanup is finished. Drain it, then release.
            while not preflight.done():
                try:
                    await asyncio.shield(preflight)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            try:
                preflight.result()
            except Exception:
                pass
            try:
                cleanup = asyncio.create_task(self.stop(delete=True))
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
            finally:
                self._release_owner()
            raise

    def _release_owner(self):
        if self._owner_lock is not None:
            self._owner_lock.close()
            self._owner_lock = None

    async def stop(self, delete):
        cleanup = asyncio.create_task(self._stop_owned(delete))
        cancelled = False
        try:
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
            if cancelled:
                raise asyncio.CancelledError
        finally:
            self._release_owner()

    async def _stop_owned(self, delete):
        if self._private is None:
            self._release_owner()
            return
        if not self._compose_started:
            # Validation/build failed before any Compose up. In particular,
            # never run down against a foreign named-volume collision.
            self._cleanup_mounts_compose_file()
            self._cleanup_resources_compose_file()
            self._cleanup_env_compose_file()
            self._cleanup_egress_control_services_compose_file()
            self._gateway_overlay = None
            self._private.cleanup()
            self._private = None
            return
        await self._stop_heartbeat()
        self._heartbeat_error = RuntimeError("Environment teardown requested; create a new environment")
        await asyncio.to_thread(self._check_resource_ownership, self._rendered_document)
        try:
            await self._force_closed()
        except Exception:
            pass  # down below must succeed, not merely log a cleanup failure.
        try:
            await self.prepare_logs_for_host()
        except Exception:
            pass
        # Host-owned audit output is outside every task mount. It contains only
        # controller events/hash/packet counts, never proxy/DNS payloads.
        audit_dir = self.trial_paths.trial_dir / "egress"
        audit_error = False
        try:
            audit_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            logs = await self._run_docker_compose_command(["logs", "--no-color", SERVICE], timeout_sec=15)
            (audit_dir / f"{self._instance}.log").write_text(logs.stdout)
        except Exception:
            audit_error = True
        command = ["down", "--remove-orphans"]
        if delete:
            command.append("--volumes")
        try:
            await self._run_docker_compose_command(command, timeout_sec=60)
        except BaseException:
            # Preserve credentials/manifest in the owner-only directory for
            # verified recovery; never pretend that Docker down succeeded.
            self._release_owner()
            raise
        self._cleanup_mounts_compose_file()
        self._cleanup_resources_compose_file()
        self._cleanup_env_compose_file()
        self._cleanup_egress_control_services_compose_file()
        self._gateway_overlay = None
        # Harbor's delete=False retains named volumes. Keep their recoverable
        # owner manifest too; otherwise the next start cannot safely adopt them.
        if delete or not self._rendered_document.get("volumes"):
            self._private.cleanup()
        else:
            (Path(self._private.name) / "input.json").unlink(missing_ok=True)
        self._private = None
        self._compose_started = False
        self._release_owner()
        if audit_error:
            raise RuntimeError("Gateway removed, but policy audit collection failed")
