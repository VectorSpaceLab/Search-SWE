"""Command-line entrypoint for configuration and evaluation batches."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from . import __version__
from .configuration import DEFAULTS, Setting, read_env, save_env, check_config_destination
from .repository import discover, find_repo, select_tasks
from .resources import Pool
from . import runner


def parser():
    root = argparse.ArgumentParser(prog="search-swe", description="Configure and run Search-SWE evaluations")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--repo", type=Path, help="Search-SWE checkout (or SEARCH_SWE_REPO)")
    commands = root.add_subparsers(dest="command")
    for name in ("run", "configure", "list", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
        if name in ("list", "doctor"):
            command.add_argument("--json", action="store_true")
        if name == "list":
            command.add_argument("--hardware", choices=("cpu", "gpu"))
        if name not in ("run", "configure"):
            continue
        command.add_argument("tasks", nargs="*", help="Task names; omit for the interactive selector")
        command.add_argument("--task", action="append", default=[], help="Select a task; repeat for multiple tasks")
        command.add_argument("--model")
        command.add_argument("--agent", choices=("codex", "claude-code", "pi"))
        command.add_argument("--provider", choices=("openrouter", "direct"))
        command.add_argument("--reasoning-effort", help="Reasoning effort / Pi thinking level, or default to omit the override")
        command.add_argument("--refresh-models", action="store_true", help="Refresh the OpenRouter catalog during interactive model selection")
        command.add_argument("--env-file", type=Path, help="Defaults to the checkout .env")
        command.add_argument("--concurrency", type=int, help="Maximum concurrent tasks; default 1")
        command.add_argument("--cpu-set", help="CPU pool, e.g. 0-31")
        command.add_argument("--gpu-devices", help="GPU pool: comma-separated indices or full UUIDs")
        command.add_argument("--memory-gb", type=float, help="Cap the batch RAM pool in GiB")
        command.add_argument("--output", type=Path, help="Fresh batch output directory")
        command.add_argument("--offline", action="store_true", help="Use cached assets/model catalog; evaluation API calls still need network")
        command.add_argument("--dry-run", action="store_true", help="Show the setting/tasks without prompts, writes, downloads or API calls")
        command.add_argument("--yes", action="store_true", help="Use arguments/saved configuration without interactive prompts")
    return root


def configure_run(args, root):
    catalog = discover(root)
    path = (args.env_file or root / ".env").expanduser().absolute()
    file_values = read_env(path)
    env = {**DEFAULTS, **file_values, **os.environ}
    env = {key: value for key, value in env.items() if value is not None}
    current = Setting(args.agent or env.get("SEARCH_SWE_AGENT") or "codex",
                      args.provider or env.get("SEARCH_SWE_PROVIDER") or "openrouter",
                      args.model or env.get("AGENT_MODEL") or "openai/gpt-6-luna",
                      args.reasoning_effort or env.get("PI_THINKING" if (args.agent or env.get("SEARCH_SWE_AGENT")) == "pi" else "AGENT_REASONING_EFFORT") or "max")
    interactive = not args.yes and not args.dry_run
    if interactive and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError("Interactive setup needs a terminal; provide task/configuration arguments and --yes for scripts")
    updates = {}
    setting = current
    if interactive:
        from . import wizard
        print("Search-SWE evaluation setup. API keys are entered privately and never displayed.")
        setting = wizard.select_setting(current, args)
    setting.validate()
    updates.update(setting.values())
    env.update(updates)
    if interactive:
        wizard.configure_agent(setting, env, updates)
    names = [*args.tasks, *args.task]
    tasks = select_tasks(catalog, names) if names else []
    if not tasks and interactive:
        tasks = wizard.select_tasks(catalog)
    if not tasks:
        raise ValueError("Select at least one task; use search-swe list")
    if interactive:
        wizard.configure_task_services(tasks, env, updates)
    concurrency = (wizard.concurrency(args.concurrency) if interactive else
                   args.concurrency if args.concurrency is not None else int(env.get("SEARCH_SWE_CONCURRENCY") or "1"))
    if concurrency < 1:
        raise ValueError("--concurrency must be positive")
    if interactive and args.command == "run" and any(task.gpus for task in tasks) and not args.gpu_devices:
        args.gpu_devices = wizard.gpu_pool()
    updates["SEARCH_SWE_CONCURRENCY"] = str(concurrency)
    required = setting.required() | set().union(*(task.required_variables() for task in tasks))
    # Persist required default endpoints along with the explicitly entered keys.
    for key in required:
        if env.get(key) and key not in file_values and key not in os.environ:
            updates.setdefault(key, env[key])
    summary = {"setting": setting.public(), "tasks": [task.name for task in tasks],
               "concurrency": concurrency, "asset_gib": round(sum(task.asset_bytes for task in tasks) / 2**30, 2),
               "resource_pool": {"cpus": args.cpu_set or "auto", "gpus": args.gpu_devices or "auto",
                                 "memory_gib_cap": args.memory_gb},
               "output": str(args.output.absolute()) if args.output else "jobs/evaluations/<unique-run>/"}
    print(json.dumps(summary, indent=2), flush=True)
    if args.dry_run:
        for task in tasks:
            subprocess.run([*runner.launch_command(root, task, setting), "--dry-run"], env=env, check=True)
        return 0
    missing = sorted(key for key in required if not env.get(key))
    if missing:
        raise ValueError("Configure these variables in .env or run search-swe configure: " + ", ".join(missing))
    runner.preflight(root, tasks, setting, env)
    pool = None
    if args.command == "run":
        runner.doctor(root, tasks, env)
        pool = Pool.host(tasks, args.cpu_set, args.gpu_devices, args.memory_gb)
        pool.validate(tasks, env)
        print(f"Resource pool: {len(pool.cpus)} logical CPUs, {pool.memory_mb / 1024:.1f} GiB RAM, {len(pool.gpus)} GPUs")
    persist = args.command == "configure"
    if interactive:
        persist = wizard.ask(wizard.questionary.confirm(f"Save settings and entered keys to {path} (mode 0600)?",
                                                       default=True, auto_enter=False))
        if persist:
            shadowed = sorted(key for key in updates if key in os.environ and os.environ[key] != updates[key])
            if shadowed:
                print("Future runs will use exported shell values ahead of saved values for: " + ", ".join(shadowed))
        action = ("Save configuration" if persist else "Finish configuration") if args.command == "configure" else "Start these evaluations (model API usage may be billed)"
        if not wizard.ask(wizard.questionary.confirm(action + "?", default=args.command == "configure", auto_enter=False)):
            print("Cancelled; configuration was not changed.")
            return 0
    if persist:
        check_config_destination(root, path)
        save_env(path, updates)
        print(f"Saved configuration to {path}; API keys are hidden.")
    if args.command == "configure":
        print("Configuration checked. No evaluation started.")
        return 0
    return runner.run_batch(root, tasks, setting, env, pool, concurrency, args.output, args.offline)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = ["run"]
    command_parser = parser()
    args = command_parser.parse_args(arguments)
    if args.command is None:
        command_parser.print_help()
        return 0
    try:
        try:
            root = find_repo(args.repo)
        except ValueError:
            interactive = (args.command in ("run", "configure")
                           and not args.yes and not args.dry_run
                           and sys.stdin.isatty() and sys.stdout.isatty())
            if args.repo or os.environ.get("SEARCH_SWE_REPO") or not interactive:
                raise
            from .wizard import select_repository
            root = select_repository(offline=args.offline)
        if args.command == "list":
            rows = [{"name": task.name, "cpus": task.cpus, "ram_gib": task.memory_mb / 1024,
                     "gpus": task.gpus, "asset_gib": round(task.asset_bytes / 2**30, 2)}
                    for task in discover(root).values()
                    if args.hardware is None or bool(task.gpus) == (args.hardware == "gpu")]
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    print(f"{row['name']:<42} {row['cpus']:>3} CPU  {row['ram_gib']:>5g} GiB RAM  {row['gpus']} GPU  {row['asset_gib']:>7.2f} GiB assets")
            return 0
        if args.command == "doctor":
            result = runner.doctor(root)
            print(json.dumps(result, indent=2) if args.json else "\n".join(f"{key}: {value}" for key, value in result.items()))
            return 0
        return configure_run(args, root)
    except KeyboardInterrupt:
        print("Cancelled; inspect the batch summary if execution had started.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
