"""Strict public configuration; credentials are loaded only by the host adapter."""

from dataclasses import dataclass, field
from importlib.metadata import version
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


HOST = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
DEFAULT_IMAGE = "hanhainebula/search-swe-egress:1.0.0"


def require_supported_harbor():
    if version("harbor") != "0.22.0":
        raise ValueError("Restricted egress is currently validated only against Harbor 0.22.0")


def exact_hosts(hosts):
    if not isinstance(hosts, (list, tuple)) or any(not isinstance(h, str) or not HOST.fullmatch(h) for h in hosts):
        raise ValueError("Restricted egress supports only lowercase exact DNS hosts (no IP/CIDR/wildcards)")
    return sorted(set(hosts))


def check_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError("Invalid restricted-egress configuration keys")


def endpoint(value, *, doh=False):
    try:
        if not isinstance(value, str) or any(ord(c) <= 32 for c in value):
            raise ValueError()
        parsed = urlsplit(value)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if (parsed.scheme not in ({"https"} if doh else {"http", "https"})
                or not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or not 1 <= port <= 65535
                or (not doh and parsed.path not in {"", "/"})):
            raise ValueError()
        if not HOST.fullmatch(parsed.hostname):
            ipaddress.IPv4Address(parsed.hostname)
        return parsed, port
    except (ValueError, TypeError):
        # Never echo the supplied URL: rejected input may contain a password.
        raise ValueError("Invalid egress endpoint: use HTTP(S), no userinfo/query/fragment; DoH requires HTTPS") from None


def read_auth(path):
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("Proxy credential directory must be owned by the current user and mode 0700")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("Proxy credential file must be owned by the current user and mode 0600")
        try:
            content = stream.read(16385)
            if len(content) > 16384:
                raise ValueError()
            auth = json.loads(content)
            check_keys(auth, {"username", "password"})
            if any(not isinstance(auth[k], str) or not auth[k] or len(auth[k]) > 4096 for k in auth):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Proxy credential file must contain a bounded username/password JSON object") from None
    return auth


@dataclass(frozen=True)
class EgressConfig:
    path: Path | None
    image: str
    settings: dict = field(repr=False)
    auth_path: Path | None = field(default=None, repr=False)

    def private_settings(self):
        settings = dict(self.settings)
        if self.auth_path is not None:
            settings["auth"] = read_auth(self.auth_path)
        return settings


def direct_config(image=DEFAULT_IMAGE, dns_servers=None, path=None):
    """Docker's embedded resolver is used only by the trusted DNS worker."""
    validate_image(image)
    servers = ["127.0.0.11"] if dns_servers is None else dns_servers
    if not isinstance(servers, list) or not servers:
        raise ValueError("Direct DNS requires a nonempty list of IPv4 servers")
    for value in servers:
        try:
            if not isinstance(value, str):
                raise ValueError()
            host, separator, port = value.partition(":")
            if separator and (not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535):
                raise ValueError()
            address = ipaddress.IPv4Address(host)
            if (address.is_unspecified or address.is_multicast
                    or address.is_link_local or address.is_reserved
                    or (address.is_loopback and (host != "127.0.0.11" or (separator and int(port) != 53)))):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Direct DNS requires IPv4 servers reachable from Docker; only Docker's 127.0.0.11 loopback resolver is supported") from None
    return EgressConfig(path, image, {"transport": "direct", "dns_servers": list(dict.fromkeys(servers))})


def validate_image(image):
    if (not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@-]*", image)
            or "://" in image
            or ("@" in image and not re.search(r"@sha256:[0-9a-f]{64}\Z", image))):
        raise ValueError("Gateway image must be a valid image name or sha256 digest reference")


def load_config(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("EGRESS_CONFIG must be a regular, single-link file")
    try:
        document = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise ValueError("EGRESS_CONFIG must be a JSON object") from None
    check_keys(document, {"version", "image", "dns"}, {"upstream", "mode"})
    if type(document["version"]) is not int or document["version"] != 1:
        raise ValueError("Unsupported EGRESS_CONFIG version")
    validate_image(document["image"])
    mode = document.get("mode", "proxy")
    if mode == "direct":
        if "upstream" in document:
            raise ValueError("Direct egress must not specify an upstream proxy")
        check_keys(document["dns"], set(), {"servers"})
        return direct_config(document["image"], document["dns"].get("servers"), path)
    if mode != "proxy" or "upstream" not in document:
        raise ValueError("Egress mode must be direct or proxy; proxy requires upstream")
    upstream, dns = document["upstream"], document["dns"]
    check_keys(upstream, {"url"}, {"address", "auth_file"})
    check_keys(dns, {"doh_url"})
    parsed, port = endpoint(upstream["url"])
    endpoint(dns["doh_url"], doh=True)
    # Bootstrap the operator's proxy independently of potentially polluted
    # container DNS. HTTPS still verifies the URL hostname, not this address.
    try:
        address = upstream.get("address", parsed.hostname)
        if not isinstance(address, str):
            raise ValueError()
        parsed_address = ipaddress.IPv4Address(address)
        if (parsed_address.is_loopback or parsed_address.is_unspecified or parsed_address.is_multicast
                or parsed_address.is_link_local or parsed_address.is_reserved):
            raise ValueError()
        address = str(parsed_address)
    except (ValueError, TypeError):
        raise ValueError("Upstream requires an explicit IPv4 address outside the task namespace; loopback/link-local are unsupported") from None
    settings = {"upstream_addr": f"{address}:{port}", "upstream_ip": address, "upstream_port": port,
                "upstream_host": parsed.hostname, "upstream_tls": parsed.scheme == "https",
                "doh_url": dns["doh_url"]}
    auth_path = None
    if "auth_file" in upstream:
        if not isinstance(upstream["auth_file"], str) or not upstream["auth_file"]:
            raise ValueError("upstream.auth_file must be a nonempty path")
        # Do not resolve the final component: read_auth rejects symlinks.
        auth_path = path.parent / Path(upstream["auth_file"]).expanduser()
    return EgressConfig(path, document["image"], settings, auth_path)


def validate_task_networks(task_path, model_host, proxy_host=None, *, allow_public=False):
    """Use Harbor's real per-step resolver, never a union or parallel TOML model."""
    require_supported_harbor()
    from harbor.models.task.config import TaskConfig, TaskOS
    from harbor.models.task.verifier_mode import (
        resolve_effective_verifier_env_config, resolve_step_verifier_mode, resolve_task_verifier_mode,
    )
    from harbor.models.trial.config import AgentConfig, EnvironmentConfig
    from harbor.trial.network_policy import resolve_trial_network_plan

    task = TaskConfig.model_validate_toml((Path(task_path) / "task.toml").read_text())
    if task.environment.os != TaskOS.LINUX:
        raise ValueError("Restricted egress currently requires Linux task environments")
    restricted = False
    for step in task.steps or [None]:
        verifier = resolve_effective_verifier_env_config(task, step)
        if verifier is not None and verifier.os != TaskOS.LINUX:
            raise ValueError("Restricted egress currently requires Linux verifier environments")
        mode = resolve_task_verifier_mode(task) if step is None else resolve_step_verifier_mode(task, step)
        plan = resolve_trial_network_plan(
            task, AgentConfig(extra_allowed_hosts=[model_host] if model_host else []),
            EnvironmentConfig(), step, verifier_mode=mode, env_config=verifier)
        for policy in (plan.agent_env_baseline, plan.agent_phase, plan.verifier_env_baseline, plan.verifier_phase):
            if policy is None:
                continue
            if policy.network_mode.value not in {"allowlist", "no-network"}:
                if not allow_public:
                    raise ValueError("Restricted proxy egress does not support tasks with any public phase")
                continue
            restricted = True
            exact_hosts(policy.allowed_hosts)
            if proxy_host in policy.allowed_hosts:
                raise ValueError("A general upstream proxy cannot also be an allowed task/API destination")
    return restricted
