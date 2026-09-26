#!/usr/bin/env python3
"""Launch a Search-SWE task with separately configured agent and judge services."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import sys
import tomllib
from urllib.parse import urlsplit

if __package__:
    from .docker_dns import parse_servers
    from .task_paths import select_task, task_key
    from .download_assets import destination_path, read_manifest, relative_path
else:
    from docker_dns import parse_servers
    from task_paths import select_task, task_key
    from download_assets import destination_path, read_manifest, relative_path


REPO = Path(__file__).resolve().parents[1]
TASKS = tuple(sorted(path.parent.name for path in (REPO / "tasks").glob("*/task.toml")))
CODEX_VERSION = "0.147.0"
CLAUDE_CODE_VERSION = "2.1.273"
CLAUDE_CODE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
ANTHROPIC_HOST = "api.anthropic.com"
CLAUDE_HOST_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_FORCE_OAUTH",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "AWS_BEARER_TOKEN_BEDROCK",
)
PI_VERSION = "0.85.1"
PI_THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh")
PI_MODEL_KEYS = {
    "deepseek/deepseek-flash": "DEEPSEEK_API_KEY",
    "zai/glm-5.3-flash": "ZAI_API_KEY",
}
PI_MODEL_HOSTS = {
    "deepseek/deepseek-flash": "api.deepseek.com",
    "zai/glm-5.3-flash": "api.z.ai",
}
AGENT_IMPORTS = {
    "claude-code": "scripts.harbor_agents:PreinstalledClaudeCode",
    "codex": "scripts.harbor_agents:PreinstalledCodex",
    "pi": "scripts.harbor_agents:PreinstalledPi",
}


def endpoint_hostname(value, variable):
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{variable} has an invalid port") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{variable} must be an absolute HTTP(S) URL without credentials, "
            "query, or fragment"
        )
    del port
    return parsed.hostname.lower().rstrip(".")


def effective_network_policy(task_config, phase):
    baseline = task_config.get("environment", {})
    override = task_config.get(phase, {})
    mode = override.get("network_mode", baseline.get("network_mode", "public"))
    hosts = override.get("allowed_hosts", baseline.get("allowed_hosts", []))
    return mode, hosts


def host_is_allowed(host, allowed_hosts):
    return any(
        host == entry
        or (entry.startswith("*.") and host.endswith(entry[1:]))
        for entry in allowed_hosts
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--task", choices=TASKS)
    selection.add_argument("--task-path", help="Explicit repository-relative package, including a reviewed submission")
    parser.add_argument("--agent", default="codex", choices=tuple(AGENT_IMPORTS))
    parser.add_argument("--model", help="Agent model; defaults to AGENT_MODEL")
    parser.add_argument("--env-file", type=Path, help="Defaults to the repository .env if present")
    parser.add_argument(
        "--reasoning-effort",
        help="Override AGENT_REASONING_EFFORT for Codex or Claude Code",
    )
    parser.add_argument("--codex-config", type=Path, help="Optional native Codex TOML configuration")
    parser.add_argument("--thinking", choices=PI_THINKING_LEVELS, help="Pi thinking level; overrides PI_THINKING")
    parser.add_argument("--container-dns", help="Comma-separated upstream IPv4 DNS servers; overrides CONTAINER_DNS. Keeps Harbor's API allowlist.")
    parser.add_argument("--egress-config", type=Path, help="Direct/proxy gateway JSON; overrides EGRESS_CONFIG. Without it, restricted tasks use the direct gateway.")
    parser.add_argument("--egress-image", help="Direct gateway image (pulled if missing); overrides EGRESS_IMAGE. Cannot be combined with EGRESS_CONFIG.")
    parser.add_argument("--output", type=Path, help="Job output directory; relative to the current directory")
    parser.add_argument("--dry-run", action="store_true", help="Print the command with variable references; do not launch")
    args = parser.parse_args()

    env_file = args.env_file or REPO / ".env"
    file_env = {}
    if env_file.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:
            parser.error("python-dotenv is required; use the Python environment containing Harbor")
        # Read values as data: never execute shell code or expand credentials.
        file_env = {key: value for key, value in dotenv_values(env_file, interpolate=False).items() if value is not None}
    elif args.env_file is not None:
        parser.error(f"Environment file does not exist: {env_file}")
    env = {**file_env, **os.environ}
    egress_path = args.egress_config or (REPO / env["EGRESS_CONFIG"] if env.get("EGRESS_CONFIG") else None)
    dns_servers = None
    if dns_value := (args.container_dns or env.get("CONTAINER_DNS")):
        try:
            dns_servers = parse_servers(dns_value)
        except ValueError as error:
            parser.error(f"Invalid CONTAINER_DNS: {error}")
    model = args.model or env.get("AGENT_MODEL")
    if not model:
        parser.error("Set --model or AGENT_MODEL")
    if args.agent == "pi":
        if model not in PI_MODEL_KEYS:
            parser.error(
                f"Unsupported Pi model: {model}. Supported Pi models: "
                + ", ".join(PI_MODEL_KEYS)
            )
        if args.reasoning_effort is not None:
            parser.error(
                "--reasoning-effort is only valid with --agent codex or claude-code"
            )
        if args.codex_config is not None:
            parser.error("--codex-config is only valid with --agent codex")
    else:
        if args.thinking is not None:
            parser.error("--thinking is only valid with --agent pi")
        if args.agent == "claude-code":
            if args.codex_config is not None:
                parser.error("--codex-config is only valid with --agent codex")
            effort = args.reasoning_effort or env.get("AGENT_REASONING_EFFORT")
            if effort and effort not in CLAUDE_CODE_EFFORT_LEVELS:
                parser.error(
                    "Claude Code reasoning effort must be one of: "
                    + ", ".join(CLAUDE_CODE_EFFORT_LEVELS)
                )

    try:
        task = select_task(REPO, args.task_path or f"tasks/{args.task}")
    except ValueError as error:
        parser.error(str(error))
    task_config = tomllib.loads((task / "task.toml").read_text())
    verifier_env = task_config.get("verifier", {}).get("env", {})
    output = args.output.resolve() if args.output else REPO / "jobs" / task_key(REPO, task)
    command = [
        "harbor", "run", "--path", str(task), "--env", "docker",
        "--agent", AGENT_IMPORTS[args.agent], "--force-build", "--yes", "-o", str(output),
        "--agent-setup-timeout-multiplier", "3", "-m", model,
        "--n-concurrent", "1", "--n-attempts", "1", "--max-retries", "0",
    ]
    # Harbor 0.22.0 rejects Docker tasks with gpus > 0 before Compose starts
    # and does not translate that field into a Docker GPU request. Preserve the
    # truthful task metadata while the task's Compose overlays allocate the GPU.
    if task_config.get("environment", {}).get("gpus", 0) > 0:
        command.extend(["--override-gpus", "0"])
    required = []
    agent_host = None
    if args.agent == "codex":
        command.extend(["--ak", f"version={CODEX_VERSION}"])
        effort = args.reasoning_effort or env.get("AGENT_REASONING_EFFORT")
        if effort:
            command.extend(["--ak", f"reasoning_effort={effort}"])
        config = args.codex_config
        if config is None and env.get("AGENT_CODEX_CONFIG"):
            config = REPO / env["AGENT_CODEX_CONFIG"]
        if config is not None:
            config = config.resolve()
            if not config.is_file():
                parser.error(f"Codex configuration does not exist: {config}")
            command.extend(["--ak", f"config={config}"])
        for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY"):
            source = f"AGENT_{name}"
            required.append(source)
            # Harbor resolves these from its environment. Secrets do not enter argv.
            command.extend(["--ae", f"{name}=${{{source}}}"])
        if env.get("AGENT_OPENAI_BASE_URL"):
            try:
                agent_host = endpoint_hostname(
                    env["AGENT_OPENAI_BASE_URL"], "AGENT_OPENAI_BASE_URL"
                )
            except ValueError as error:
                parser.error(str(error))
    elif args.agent == "claude-code":
        command.extend(["--ak", f"version={CLAUDE_CODE_VERSION}"])
        effort = args.reasoning_effort or env.get("AGENT_REASONING_EFFORT")
        if effort:
            command.extend(["--ak", f"reasoning_effort={effort}"])
        required.append("AGENT_ANTHROPIC_API_KEY")
        command.extend(
            [
                "--ae",
                "ANTHROPIC_API_KEY=${AGENT_ANTHROPIC_API_KEY}",
            ]
        )
        agent_host = ANTHROPIC_HOST
    else:
        thinking = args.thinking or env.get("PI_THINKING")
        if thinking and thinking not in PI_THINKING_LEVELS:
            parser.error(
                "PI_THINKING must be one of: " + ", ".join(PI_THINKING_LEVELS)
            )
        command.extend(["--ak", f"version={PI_VERSION}"])
        if thinking:
            command.extend(["--ak", f"thinking={thinking}"])
        key = PI_MODEL_KEYS[model]
        required.append(key)
        command.extend(["--ae", f"{key}=${{{key}}}"])
        agent_host = PI_MODEL_HOSTS[model]

    agent_network_mode, _ = effective_network_policy(task_config, "agent")
    verifier_network_mode, verifier_allowed_hosts = effective_network_policy(
        task_config, "verifier"
    )
    agent_requires_host = any(step.get("agent", {}).get("network_mode", agent_network_mode) != "public"
                              for step in task_config.get("steps") or [{}])
    if agent_requires_host:
        if agent_host is None:
            parser.error(
                "Set AGENT_OPENAI_BASE_URL so Harbor can allow only the selected "
                "coding-model host"
            )
        command.extend(["--allow-agent-host", agent_host])

    if "OPENAI_API_KEY" in verifier_env:
        for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY"):
            source = f"VERIFIER_{name}"
            required.append(source)
            command.extend(["--verifier-env", f"{name}=${{{source}}}"])

    # Task-specific judge settings are resolved by task.toml from Harbor's
    # environment; require only the groups used by the selected task.
    for name in ("ANSWER_JUDGE_MODEL_NAME", "ANSWER_JUDGE_BASE_URL", "ANSWER_JUDGE_API_KEY"):
        if name in verifier_env:
            required.append(name)

    endpoint_variables = []
    if "OPENAI_API_KEY" in verifier_env:
        endpoint_variables.append("VERIFIER_OPENAI_BASE_URL")
    if "ANSWER_JUDGE_BASE_URL" in verifier_env:
        endpoint_variables.append("ANSWER_JUDGE_BASE_URL")
    for variable in endpoint_variables:
        if not env.get(variable):
            continue
        try:
            host = endpoint_hostname(env[variable], variable)
        except ValueError as error:
            parser.error(str(error))
        if verifier_network_mode == "no-network":
            parser.error(f"{variable} cannot be used with verifier network_mode=no-network")
        if verifier_network_mode == "allowlist" and not host_is_allowed(
            host, verifier_allowed_hosts
        ):
            parser.error(
                f"{variable} host {host!r} is not permitted by the task's "
                "[verifier].allowed_hosts"
            )

    if __package__:
        from .egress.config import DEFAULT_IMAGE, direct_config, load_config, validate_task_networks
    else:
        from egress.config import DEFAULT_IMAGE, direct_config, load_config, validate_task_networks
    egress_image = args.egress_image or env.get("EGRESS_IMAGE")
    try:
        if egress_path is not None:
            if dns_servers or env.get("CONTAINER_PROXY") or egress_image:
                parser.error("EGRESS_CONFIG cannot be combined with CONTAINER_DNS/--container-dns, CONTAINER_PROXY, or EGRESS_IMAGE/--egress-image; clear them explicitly")
            egress = load_config(egress_path)
        else:
            egress = direct_config(egress_image or DEFAULT_IMAGE, dns_servers)
        restricted = validate_task_networks(task, agent_host, egress.settings.get("upstream_host"),
                                            allow_public=egress.settings.get("transport") == "direct")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    use_gateway = restricted or egress_path is not None

    if env.get("CONTAINER_PROXY"):
        if restricted:
            parser.error(
                "CONTAINER_PROXY is incompatible with this task's Harbor network "
                "allowlists because a general proxy can bypass destination filtering"
            )
        env.setdefault("CONTAINER_NO_PROXY", "127.0.0.1,localhost")
        for flag in ("--ae", "--verifier-env"):
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
                command.extend([flag, f"{name}=${{CONTAINER_PROXY}}"])
            for name in ("no_proxy", "NO_PROXY"):
                command.extend([flag, f"{name}=${{CONTAINER_NO_PROXY}}"])

    if use_gateway:
        command[command.index("--env") + 1] = "scripts.harbor_environments:PhaseScopedDocker"
        if egress_path is not None:
            command.extend(["--environment-kwarg", f"egress_config={egress.path}"])
        else:
            command.extend(["--environment-kwarg", f"egress_image={egress.image}"])
            if dns_servers:
                command.extend(["--environment-kwarg", "egress_dns=" + ",".join(dns_servers)])

    # This launcher uses explicit API keys, without consulting a host auth.json.
    env.pop("CODEX_AUTH_JSON_PATH", None)
    env.pop("CODEX_FORCE_AUTH_JSON", None)
    if args.agent == "claude-code":
        for name in CLAUDE_HOST_ENV_VARS:
            env.pop(name, None)

    if args.dry_run:
        print("Preview only; credentials, assets, Docker, GPU, and API access are not checked.")
        if use_gateway:
            mode = egress.settings.get("transport", "proxy")
            print(f"Phase-scoped {mode} gateway; task and phase allowlists are enforced by the trusted sidecar.")
        if dns_servers:
            print("Trusted gateway DNS servers: " + ", ".join(dns_servers))
        print("Environment values are passed to Harbor separately from the command:")
        print(shlex.join(command))
        return 0

    missing = [name for name in required if not env.get(name)]
    if missing:
        parser.error("Set the following variables in .env or the shell: " + ", ".join(missing))
    manifest = read_manifest(task)
    unavailable = []
    for entry in manifest["files"]:
        path = destination_path(task, relative_path(entry["path"]))
        if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
            unavailable.append(entry["path"])
    if unavailable:
        selection_flag = f"--task-path {args.task_path}" if args.task_path else f"--task {args.task}"
        parser.error(f"Run python scripts/download_assets.py {selection_flag} to restore the missing or incomplete assets: " + ", ".join(unavailable))
    if shutil.which("harbor", path=env.get("PATH")) is None:
        parser.error("harbor was not found; activate the supported Harbor environment")
    if dns_servers and not use_gateway:
        parser.error("CONTAINER_DNS requires a restricted task or an explicit direct EGRESS_CONFIG")

    # Harbor is a console script: changing cwd alone does not put this checkout
    # on its interpreter's search path for scripts.harbor_agents.
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(REPO)
    if existing_pythonpath:
        env["PYTHONPATH"] += os.pathsep + existing_pythonpath

    print(f"Launching {task_key(REPO, task)}; job output: {output}", flush=True)
    # All task and output paths are absolute, so launching works from any directory.
    os.chdir(REPO)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    sys.exit(main())
