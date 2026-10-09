"""Reject unsupported topology before launch; verify the final merged Compose."""

import os
from pathlib import Path
import stat


SERVICE = "harbor-docker-egress-control-sidecar"
NETWORK = f"service:{SERVICE}"


def declared_services(documents):
    names = {"main"}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Invalid Compose document")
        if document.get("networks"):
            raise ValueError("Explicit Compose networks are not supported with restricted egress")
        for name, service in document.get("services", {}).items():
            if name == SERVICE:
                raise ValueError("Task Compose cannot define the trusted egress service")
            if not isinstance(service, dict) or "network_mode" in service or "networks" in service:
                raise ValueError("Explicit service networking is not supported with restricted egress")
            names.add(name)
    return sorted(names)


def validate_final(document, *, private_directory, image, engine_paths=(), protected_paths=()):
    if document.get("configs") or document.get("secrets"):
        raise ValueError("Compose config/secret objects are unsupported with restricted egress")
    services = document.get("services", {})
    if SERVICE not in services or "main" not in services:
        raise ValueError("Restricted-egress Compose is missing required services")
    gateway = services[SERVICE]
    if gateway.get("image") != image or gateway.get("entrypoint") != ["/opt/egress-sidecar/entrypoint.sh"]:
        raise ValueError("Trusted gateway image/entrypoint was overridden")
    if gateway.get("network_mode") or set(gateway.get("networks", {})) != {"default"}:
        raise ValueError("Gateway must use its own default Compose network")
    if gateway.get("ports") or gateway.get("privileged") or gateway.get("pid") or gateway.get("ipc") == "host":
        raise ValueError("Unsupported trusted gateway topology")
    if not gateway.get("read_only") or "/run/searchswe:mode=0700" not in gateway.get("tmpfs", []):
        raise ValueError("Gateway runtime credentials must remain on private tmpfs")
    private = Path(private_directory).resolve()

    def check_private_source(source):
        source = Path(source).resolve()
        if source == private or source in private.parents or private in source.parents:
            raise ValueError("Untrusted service can read the private gateway directory")
        for protected in protected_paths:
            protected = Path(protected).resolve()
            if source == protected or source in protected.parents or protected in source.parents:
                raise ValueError("Untrusted service can access gateway configuration or proxy credentials")
        controls = {Path(p).resolve() for p in ("/proc", "/sys", "/dev", "/run", "/var/lib/docker", "/var/lib/containerd", *engine_paths)}
        if any(source == control or source in control.parents or control in source.parents for control in controls):
            raise ValueError("Untrusted service has a host control mount/build context")
        return source

    for name, service in services.items():
        if name == SERVICE:
            continue
        build = service.get("build") or {}
        if build:
            if (build.get("additional_contexts") or build.get("secrets") or build.get("privileged")
                    or build.get("entitlements") or build.get("network") not in {None, "default", "none"}):
                raise ValueError("Unsupported privileged/extra-context task image build")
            context = build.get("context", "")
            if context and "://" not in context:
                check_private_source(context)
        if service.get("network_mode") != NETWORK or service.get("networks"):
            raise ValueError(f"Service {name} is not in its own trial's gateway namespace")
        dropped = {str(cap).removeprefix("CAP_").upper() for cap in service.get("cap_drop", [])}
        if "ALL" not in dropped and not {"NET_RAW", "NET_ADMIN"} <= dropped:
            raise ValueError(f"Service {name} retains network-mark capabilities")
        if service.get("cap_add") or service.get("privileged"):
            raise ValueError(f"Service {name} requests unsupported capabilities")
        if service.get("pid") or service.get("ipc") == "host" or service.get("userns_mode"):
            raise ValueError(f"Service {name} requests unsupported namespaces")
        if service.get("ports") or service.get("devices") or service.get("device_cgroup_rules"):
            raise ValueError(f"Service {name} exposes ports or raw devices")
        if service.get("configs") or service.get("secrets") or service.get("container_name"):
            raise ValueError(f"Service {name} uses unsupported configs/secrets/container names")
        if any(key.startswith("net.") for key in service.get("sysctls", {})):
            raise ValueError(f"Service {name} requests network sysctls")
        security = service.get("security_opt", [])
        if not any(s in {"no-new-privileges:true", "no-new-privileges"} for s in security):
            raise ValueError(f"Service {name} is missing no-new-privileges")
        if any("unconfined" in s for s in security):
            raise ValueError(f"Service {name} disables a security profile")
        if service.get("depends_on", {}).get(SERVICE, {}).get("condition") != "service_healthy":
            raise ValueError(f"Service {name} can start before gateway readiness")
        for mount in service.get("volumes", []):
            if mount.get("type") != "bind":
                continue
            source = check_private_source(mount["source"])
            # Sockets and host kernel control mounts permit bypassing network
            # capabilities. Task assets/log bind directories remain supported.
            if source.exists() and stat.S_ISSOCK(os.stat(source).st_mode):
                raise ValueError("Untrusted service has a host socket mount")
            if source.name in {"docker.sock", "containerd.sock", "podman.sock"}:
                raise ValueError("Untrusted service has a container-engine socket mount")
    for network in document.get("networks", {}).values():
        if network.get("external") or network.get("enable_ipv6"):
            raise ValueError("External/IPv6 Compose networks are unsupported")
    for volume in document.get("volumes", {}).values():
        if volume.get("external") or not volume.get("name", "").startswith(document.get("name", "") + "_"):
            raise ValueError("Shared/external named volumes are unsupported")
        if volume.get("driver") not in {None, "local"} or volume.get("driver_opts"):
            raise ValueError("Named volume drivers/options may bypass host mount validation")
