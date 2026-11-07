"""Install and verify versioned harnesses using a private, image-scoped cache."""

import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from search_swe import harnesses

VERSION_LINE = re.compile(r"^(?:codex-cli\s+|v)?(\d+(?:\.\d+)+(?:[A-Za-z0-9.+-]*))(?:\s+\(Claude Code\))?$")


def parse_version(output):
    versions = [match[1] for line in output.splitlines() if (match := VERSION_LINE.fullmatch(line.strip()))]
    if len(versions) != 1:
        raise RuntimeError("Harness version output must contain exactly one complete version line")
    return versions[0]


async def execute(environment, command, **kwargs):
    result = await environment.exec(command=command, **kwargs)
    if result.return_code:
        raise RuntimeError(f"Harness preparation failed: {result.stderr or result.stdout or 'command failed'}")
    return result.stdout or ""


async def image_identity(environment):
    result = await environment._run_docker_compose_command(["ps", "-q", "main"])
    container = (result.stdout or "").strip()
    if not re.fullmatch(r"[a-f0-9]{12,64}", container):
        raise RuntimeError("Cannot identify the harness installation container")
    process = await asyncio.create_subprocess_exec("docker", "inspect", "--format", "{{.Image}}", container,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20)
    value = stdout.decode().strip()
    if process.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise RuntimeError("Cannot identify the exact task image for the harness cache")
    return value


def cache_root():
    default = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "search-swe/harnesses"
    root = Path(os.environ.get("SEARCH_SWE_HARNESS_CACHE") or default).expanduser().resolve()
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("SEARCH_SWE_HARNESS_CACHE must be an owned private directory with mode 0700")
    return root


@asynccontextmanager
async def cache_lock(root, key):
    descriptor = os.open(root / (key + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(0.1)
        yield
    finally:
        os.close(descriptor)


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_cache(entry, key):
    if entry.is_symlink():
        raise ValueError("Harness cache entries must be regular directories")
    try:
        record = entry / "manifest.json"
        payload = entry / "program.tar.gz"
        if record.is_symlink() or payload.is_symlink():
            return False
        data = json.loads(record.read_text())
        return data.get("key") == key and payload.stat().st_size == data["size_bytes"] and checksum(payload) == data["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


def installation_command(spec, prefix):
    destination = shlex.quote(prefix)
    if spec["installer"] == "npm":
        package = " ".join(shlex.quote(item) for item in [spec["package"] + "@" + spec["version"],
                         *(value.format(version=spec["version"]) for value in spec.get("extra_packages", []))])
        ignore = " --ignore-scripts" if spec.get("ignore_scripts") else ""
        return (f"mkdir -p {destination}; work=$(mktemp -d); trap 'rm -rf \"$work\"' EXIT; mkdir -p \"$work/home\"; "
                'env -i PATH="$PATH" HOME="$work/home" TMPDIR="$work" '
                'HTTP_PROXY="${HTTP_PROXY:-}" HTTPS_PROXY="${HTTPS_PROXY:-}" '
                'http_proxy="${http_proxy:-}" https_proxy="${https_proxy:-}" NO_PROXY="${NO_PROXY:-}" '
                'NPM_CONFIG_USERCONFIG=/dev/null NPM_CONFIG_CACHE="$work/npm-cache" '
                f"npm install --global --prefix {destination} --registry=https://registry.npmjs.org{ignore} {package}")
    if spec["installer"] == "archive":
        url, digest, member = (shlex.quote(spec[key]) for key in ("url", "sha512", "member"))
        command = shlex.quote(spec["command"])
        return (f"mkdir -p {destination}/bin; work=$(mktemp -d); trap 'rm -rf \"$work\"' EXIT; "
                f"curl -q --fail --location --silent --show-error --connect-timeout 20 --max-time 780 {url} -o \"$work/release.tar.gz\"; "
                f"printf '%s  %s\\n' {digest} \"$work/release.tar.gz\" | sha512sum --check --status; "
                f"tar -xzf \"$work/release.tar.gz\" -C \"$work\" -- {member}; "
                f"install -m 755 \"$work/\"{member} {destination}/bin/{command}")
    raise ValueError("Unsupported harness installer in the registry")


async def verify(environment, command, expected):
    actual = parse_version(await execute(environment, command, timeout_sec=30))
    if actual != expected.removeprefix("v"):
        raise RuntimeError(f"Harness version mismatch: requested {expected}, installed {actual}")
    return actual


async def install(environment, name, version=None, logs_dir=None):
    spec = harnesses.install_spec(name, version)
    if spec is None:
        raise ValueError(f"{name} uses Harbor's native installer")
    image = await image_identity(environment)
    identity = {"schema": 1, "image": image, "spec": spec,
                "installer_sha256": checksum(Path(__file__))}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    root = cache_root()
    entry = root / key
    prefix = "/opt/search-swe/harnesses/" + name + "/" + spec["version"]
    binary = prefix + "/bin/" + spec["command"]
    remote = "/tmp/search-swe-harness-" + uuid.uuid4().hex + ".tar.gz"
    try:
        async with cache_lock(root, key):
            hit = await asyncio.to_thread(valid_cache, entry, key)
            await execute(environment, f"rm -rf -- {shlex.quote(prefix)}; mkdir -p {shlex.quote(prefix)}", user="root")
            if hit:
                await environment.upload_file(source_path=entry / "program.tar.gz", target_path=remote)
                await execute(environment, f"tar -xzf {shlex.quote(remote)} -C {shlex.quote(prefix)}", user="root")
            else:
                await execute(environment, "set -eu; " + installation_command(spec, prefix), user="root", timeout_sec=840)
            actual = await verify(environment, shlex.quote(binary) + " --version", spec["version"])
            if not hit:
                with tempfile.TemporaryDirectory(prefix=".install-", dir=root) as directory:
                    pending = Path(directory)
                    payload = pending / "program.tar.gz"
                    await execute(environment, f"tar -czf {shlex.quote(remote)} -C {shlex.quote(prefix)} .", user="root", timeout_sec=180)
                    await environment.download_file(source_path=remote, target_path=payload)
                    digest = await asyncio.to_thread(checksum, payload)
                    metadata = {"key": key, **identity, "actual_version": actual, "sha256": digest,
                                "size_bytes": payload.stat().st_size}
                    (pending / "manifest.json").write_text(json.dumps(metadata, indent=2))
                    if entry.exists():
                        shutil.rmtree(entry)
                    os.replace(pending, entry)
            # Existing/native Harbor commands resolve the same verified binary.
            name_quoted, binary_quoted = shlex.quote(spec["command"]), shlex.quote(binary)
            await execute(environment, 'mkdir -p /usr/local/bin; '
                          f'ln -sf {binary_quoted} /usr/local/bin/{name_quoted}', user="root")
            await execute(environment, 'mkdir -p "$HOME/.local/bin"; '
                          f'ln -sf {binary_quoted} "$HOME/.local/bin/"{name_quoted}')
            if name == "codex":
                # Codex dispatches its bundled patch tool by argv[0]. Keep it
                # usable even if an unprivileged task cannot create codex-path.
                await execute(environment, 'set -eu; native=$(find ' + shlex.quote(prefix) +
                              ' -type f -path "*/vendor/*/bin/codex" -print -quit); '
                              'test -n "$native"; ln -sf "$native" /usr/local/bin/apply_patch', user="root")
            runtime_path = prefix + "/bin:" + (await execute(environment, 'printf %s "$PATH"')).strip()
            if name == "gemini-cli":
                await execute(environment, 'mkdir -p "$HOME/.gemini"; if [ ! -f "$HOME/.gemini/settings.json" ]; then '
                              'printf %s \'{"experimental":{"skills":true}}\' > "$HOME/.gemini/settings.json"; fi')
            record = {"name": name, "requested_version": spec["version"], "actual_version": actual,
                      "image": image, "cache_key": key, "cache_hit": hit}
            if logs_dir is not None:
                directory = Path(logs_dir)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / "harness.json"
                with path.open("w") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(record, stream, indent=2)
            return {**record, "path": runtime_path}
    finally:
        await execute(environment, "rm -f -- " + shlex.quote(remote), user="root")


async def verify_native(agent, environment, expected):
    command = agent.get_version_command() if hasattr(agent, "get_version_command") else None
    if not command:
        if expected:
            raise ValueError("This native agent has no verifiable CLI version command; its version is controlled by Harbor")
        return
    output = await execute(environment, command, timeout_sec=30)
    actual = agent.parse_version(output)
    if expected and actual != expected.removeprefix("v"):
        # Also handle CLIs whose generic Harbor parser returns an annotated line.
        actual = parse_version(output)
        if actual != expected.removeprefix("v"):
            raise RuntimeError(f"Harness version mismatch: requested {expected}, installed {actual}")
    agent._version = actual


class ManagedHarness:
    HARNESS_NAME = None

    def __init__(self, *args, **kwargs):
        if self.HARNESS_NAME and not kwargs.get("version"):
            kwargs["version"] = harnesses.default_version(self.HARNESS_NAME)
        super().__init__(*args, **kwargs)

    async def setup(self, environment):
        from harbor.models.task.config import NetworkMode, NetworkPolicy
        from search_swe.harbor_native import SETUP_HOSTS
        if harnesses.install_spec(self.HARNESS_NAME, getattr(self, "_version", None)) is None:
            return await super().setup(environment)
        original = environment.network_policy
        policy = original if original.network_mode == NetworkMode.PUBLIC else NetworkPolicy(
            network_mode=NetworkMode.ALLOWLIST,
            allowed_hosts=sorted(set(original.allowed_hosts) | set(SETUP_HOSTS)))
        try:
            if policy != original:
                await environment.set_network_policy(policy)
            return await super().setup(environment)
        finally:
            if policy != original:
                await environment.set_network_policy(original)

    async def install(self, environment):
        if harnesses.install_spec(self.HARNESS_NAME, getattr(self, "_version", None)) is None:
            return await super().install(environment)
        result = await install(environment, self.HARNESS_NAME, self._version, self.logs_dir)
        self._version, self._harness_path = result["actual_version"], result["path"]

    async def exec_as_agent(self, environment, command, env=None, **kwargs):
        if getattr(self, "_harness_path", None):
            env = {**(env or {}), "PATH": self._harness_path}
        return await super().exec_as_agent(environment, command, env=env, **kwargs)
