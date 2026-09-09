#!/usr/bin/env python3
"""Launch a Search-SWE task with separately configured agent and judge services."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys


REPO = Path(__file__).resolve().parents[1]
TASKS = tuple(sorted(path.parent.name for path in (REPO / "tasks").glob("*/task.toml")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--agent", default="codex", choices=("codex",))
    parser.add_argument("--model", help="Agent model; defaults to AGENT_MODEL")
    parser.add_argument("--env-file", type=Path, help="Defaults to the repository .env if present")
    parser.add_argument("--reasoning-effort", help="Override AGENT_REASONING_EFFORT")
    parser.add_argument("--codex-config", type=Path, help="Optional native Codex TOML configuration")
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
    model = args.model or env.get("AGENT_MODEL")
    if not model:
        parser.error("Set --model or AGENT_MODEL")

    task = REPO / "tasks" / args.task
    output = args.output.resolve() if args.output else REPO / "jobs" / args.task
    command = [
        "harbor", "run", "--path", str(task), "--env", "docker",
        "--agent", args.agent, "--force-build", "--yes", "-o", str(output),
        "--agent-setup-timeout-multiplier", "3", "-m", model,
        "--n-concurrent", "1", "--n-attempts", "1", "--max-retries", "0",
    ]
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

    required = []
    for flag, prefix in (("--ae", "AGENT"), ("--verifier-env", "VERIFIER")):
        for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY"):
            source = f"{prefix}_{name}"
            required.append(source)
            # Harbor resolves these from its environment. Secrets do not enter argv.
            command.extend([flag, f"{name}=${{{source}}}"])

    if env.get("CONTAINER_PROXY"):
        env.setdefault("CONTAINER_NO_PROXY", "127.0.0.1,localhost")
        for flag in ("--ae", "--verifier-env"):
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
                command.extend([flag, f"{name}=${{CONTAINER_PROXY}}"])
            for name in ("no_proxy", "NO_PROXY"):
                command.extend([flag, f"{name}=${{CONTAINER_NO_PROXY}}"])

    # This launcher uses explicit API keys, without consulting a host auth.json.
    env.pop("CODEX_AUTH_JSON_PATH", None)
    env.pop("CODEX_FORCE_AUTH_JSON", None)

    if args.dry_run:
        print("Preview only; credentials, assets, Docker, GPU, and API access are not checked.")
        print("Environment values are passed to Harbor separately from the command:")
        print(shlex.join(command))
        return 0

    missing = [name for name in required if not env.get(name)]
    if missing:
        parser.error("Set the following variables in .env or the shell: " + ", ".join(missing))
    manifest = json.loads((task / "assets.json").read_text())
    unavailable = []
    for entry in manifest["files"]:
        path = task / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
            unavailable.append(entry["path"])
    if unavailable:
        parser.error(f"Run python scripts/download_assets.py --task {args.task} to restore the missing or incomplete assets: " + ", ".join(unavailable))
    if shutil.which("harbor", path=env.get("PATH")) is None:
        parser.error("harbor was not found; activate the supported Harbor environment")

    print(f"Launching {args.task}; job output: {output}", flush=True)
    # All task and output paths are absolute, so launching works from any directory.
    os.chdir(REPO)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    sys.exit(main())
