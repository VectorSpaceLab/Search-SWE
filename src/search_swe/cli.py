"""Command-line entrypoint for configuration and evaluation batches."""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from . import __version__
from .configuration import DEFAULTS, saved_setting, resolve_setting, read_env, save_env, check_config_destination
from .repository import check_compatibility, discover, find_repo, select_tasks
from .resources import Pool, cpu_ids
from .submission_models import PROFILES, display_profile, model_ids, policy_summary, profile_for_key
from .submission_checks import verify_submission_keys
from . import runner
from . import pi_models
from . import updates


def positive_int(value):
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("enter a positive integer")


def positive_float(value):
    try:
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("enter a finite positive number")


def parser():
    root = argparse.ArgumentParser(prog="search-swe", description="Configure and run Search-SWE evaluations")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--repo", type=Path, help="Search-SWE checkout (or SEARCH_SWE_REPO)")
    commands = root.add_subparsers(dest="command")
    descriptions = {
        "run": "Select tasks, check resources, restore assets and run evaluations.",
        "configure": "Save model settings, API keys and default concurrency to .env. Select optional tasks to configure their services and check submission-key restrictions.",
        "list": "List available tasks and their resource requirements.",
        "doctor": "Check the local Docker host and evaluation prerequisites.",
        "info": "Show the selected checkout, versions, task count and local Git state; works offline.",
        "update": "Fetch the current branch's upstream and apply a compatible fast-forward update.",
        "submission-models": "Show the fixed OpenRouter submission-key allowlists; works offline without a checkout.",
        "pi-models": "List Pi's supported API-key providers or their models; works offline without a checkout.",
    }
    examples = {
        "run": "Examples:\n  search-swe run\n  search-swe run reasoning-query-rewriting --yes\n  search-swe run code-embedding-finetuning --gpu-devices 0 --yes",
        "configure": "Examples:\n  search-swe configure\n  search-swe configure reasoning-query-rewriting\n  search-swe configure --model provider/model --yes",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description, description=description,
                                      epilog=examples.get(name), formatter_class=argparse.RawDescriptionHelpFormatter)
        if name not in ("submission-models", "pi-models"):
            command.add_argument("--repo", type=Path, default=argparse.SUPPRESS, help="Search-SWE checkout (or SEARCH_SWE_REPO)")
        if name in ("list", "doctor", "info", "update", "submission-models", "pi-models"):
            command.add_argument("--json", action="store_true", help="Print the result as JSON")
        if name == "submission-models":
            command.add_argument("--profile", choices=tuple(PROFILES), default="shared", help="Submission-key profile; default shared")
        if name == "pi-models":
            command.add_argument("--provider", help="Pi provider ID, e.g. google; omit to list providers")
        if name == "list":
            command.add_argument("--hardware", choices=("cpu", "gpu"), help="Show only CPU or GPU tasks")
        if name == "doctor":
            command.add_argument("--env-file", type=Path, help="Environment file; defaults to the checkout .env")
        if name == "update":
            command.add_argument("--check", action="store_true", help="Fetch and report available updates without changing checkout files")
        if name not in ("run", "configure"):
            continue
        command.set_defaults(cpu_set=None, gpu_devices=None, memory_gb=None, output=None, edit_credentials=False)
        command.add_argument("tasks", nargs="*", help="Tasks to evaluate; omit for interactive selection" if name == "run" else "Optional tasks whose service credentials should be configured")
        command.add_argument("--task", action="append", default=[], help="Select a task; repeat for multiple tasks")
        setting = command.add_argument_group("model setting")
        setting.add_argument("--agent", choices=("codex", "claude-code", "pi"), help="Coding-agent harness; saved value or codex")
        setting.add_argument("--provider", choices=("openrouter", "direct"), help="API route: OpenRouter or a direct provider")
        setting.add_argument("--model", help="Model ID; OpenRouter uses provider/model")
        setting.add_argument("--reasoning-effort", help="Reasoning / Pi thinking level; default omits the override")
        setting.add_argument("--refresh-models", action="store_true", help="Refresh the OpenRouter catalog during interactive selection")
        command.add_argument("--env-file", type=Path, help="Defaults to the checkout .env")
        if name == "configure":
            command.add_argument("--edit-credentials", action="store_true", help="Review or replace existing credentials and service settings interactively")
        command.add_argument("--concurrency", type=positive_int, help="Maximum concurrent tasks; saved value or 1")
        if name == "run":
            resources = command.add_argument_group("run resources and results")
            resources.add_argument("--cpu-set", help="CPU pool, e.g. 0-31")
            resources.add_argument("--gpu-devices", help="GPU pool: comma-separated indices or full UUIDs")
            resources.add_argument("--memory-gb", type=positive_float, help="Cap the batch RAM pool in GiB")
            resources.add_argument("--output", type=Path, help="New output directory; defaults to jobs/evaluations/<unique-run>/")
        command.add_argument("--offline", action="store_true", help="Use cached assets/model selection; submission-key checks and model calls still need network")
        command.add_argument("--dry-run", action="store_true", help="Preview settings and commands without prompts or changes" if name == "run" else "Preview configuration without prompts or changes")
        command.add_argument("--yes", action="store_true", help="Use arguments/saved configuration without interactive prompts")
    return root


def configure_run(args, root):
    check_compatibility(root)
    catalog = discover(root)
    path = (args.env_file or root / ".env").expanduser().absolute()
    file_values = read_env(path)
    env = {**DEFAULTS, **file_values, **os.environ}
    env = {key: value for key, value in env.items() if value is not None}
    current = saved_setting({**file_values, **os.environ})
    names = [*args.tasks, *args.task]
    tasks = select_tasks(catalog, names) if names else []
    if args.offline and args.refresh_models:
        raise ValueError("Choose --offline or --refresh-models")
    if args.cpu_set:
        cpu_ids(args.cpu_set)
    if args.output:
        args.output = args.output.expanduser().absolute()
        if args.output.exists():
            raise ValueError(f"Output directory already exists: {args.output}; choose a new --output directory")
    try:
        saved_concurrency = positive_int(env.get("SEARCH_SWE_CONCURRENCY") or "1") if args.concurrency is None else args.concurrency
    except argparse.ArgumentTypeError as error:
        raise ValueError("SEARCH_SWE_CONCURRENCY must be a positive integer; set it in .env or pass --concurrency") from error
    interactive = not args.yes and not args.dry_run
    if args.edit_credentials and not interactive:
        raise ValueError("--edit-credentials uses interactive prompts; omit --yes and --dry-run")
    if interactive and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError("Interactive setup needs a terminal; provide task/configuration arguments and --yes for scripts")
    updates = {}
    if interactive:
        from . import wizard
        print("Search-SWE evaluation setup. API keys are entered privately and never displayed.")
        setting = wizard.select_setting(current, args)
    else:
        setting = resolve_setting(current, args)
    updates.update(setting.values())
    env.update(updates)
    model_config = None
    if setting.agent == "pi" and not args.dry_run:
        model_config = pi_models.resolve_model_config(pi_models.native_model(setting.model, setting.provider),
                                                      offline=args.offline,
                                                      refresh=args.refresh_models and (not interactive or args.model is not None))
    if interactive:
        wizard.configure_agent(setting, env, updates, edit=args.edit_credentials)
    if not tasks and interactive:
        tasks = wizard.select_tasks(catalog, required=args.command == "run")
    if not tasks and args.command == "run":
        raise ValueError("Select at least one task; use search-swe list")
    storage = None
    if args.command == "run":
        print("Estimating asset storage from manifests and local cache (no downloads)...", flush=True)
        storage = runner.asset_plan(root, tasks, env)
        space = runner.backend(root, "assets/asset_space")
        space.describe(storage, root / "tasks")
        if not args.dry_run:
            space.validate(storage)
    if interactive and tasks:
        wizard.configure_task_services(tasks, env, updates, edit=args.edit_credentials)
    concurrency = wizard.concurrency(args.concurrency, default=saved_concurrency) if interactive else saved_concurrency
    if concurrency < 1:
        raise ValueError("--concurrency must be positive")
    if interactive and args.command == "run" and any(task.gpus for task in tasks) and not args.gpu_devices:
        args.gpu_devices = wizard.gpu_pool()
    updates["SEARCH_SWE_CONCURRENCY"] = str(concurrency)
    required = setting.required(env) | set().union(*(task.required_variables() for task in tasks))
    # Persist required default endpoints along with the explicitly entered keys.
    for key in required:
        if env.get(key) and key not in file_values and key not in os.environ:
            updates.setdefault(key, env[key])
    summary = {"setting": setting.public(), "tasks": [task.name for task in tasks],
               "concurrency": concurrency, "env_file": str(path)}
    if args.command == "run":
        summary.update(asset_gib=round(sum(task.asset_bytes for task in tasks) / 2**30, 2),
                       resource_pool={"cpus": args.cpu_set or "auto", "gpus": args.gpu_devices or "auto",
                                      "memory_gib_cap": args.memory_gb},
                       output=str(args.output) if args.output else str(root / "jobs/evaluations/<unique-run>"))
    summary["credentials"] = {
        "required": {name: "configured" if env.get(name, "").strip() else "missing" for name in sorted(required)},
        "optional": {name: "configured" if env.get(name, "").strip() else "unset"
                     for name in sorted(set().union(*(task.optional_variables() for task in tasks)) - required)},
    }
    summary["task_configuration"] = {task.name: {"resource_policy": str(task.path / "environment/docs/available_resources.md"),
                                               "variables": task.configuration()} for task in tasks if task.variables()}
    submission_profiles = {profile for task in tasks for name in task.variables()
                           if (profile := profile_for_key(name)) is not None}
    if submission_profiles:
        summary["submission_model_policies"] = [policy_summary(profile) for profile in sorted(submission_profiles)]
    print(json.dumps(summary, indent=2), flush=True)
    if args.dry_run:
        if args.command == "run":
            for task in tasks:
                subprocess.run([*runner.launch_command(root, task, setting), "--dry-run"], env=env, check=True)
        return 0
    missing = sorted(key for key in required if not env.get(key, "").strip())
    if missing:
        import shlex
        command = ["search-swe", "configure", "--repo", str(root), "--env-file", str(path),
                   "--agent", setting.agent, "--provider", setting.provider, "--model", setting.model,
                   "--reasoning-effort", setting.effort, *[task.name for task in tasks]]
        raise ValueError("Missing variables for this selection: " + ", ".join(missing) +
                         "\nFill them in the selected environment file, or run: " + shlex.join(command))
    if setting.agent == "pi":
        pi_models.agent_host(pi_models.native_model(setting.model, setting.provider), env)
    runner.preflight(root, tasks, setting, env, model_config=model_config)
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
        if (args.command == "configure" and not persist) or (args.command == "run" and not wizard.ask(
                wizard.questionary.confirm("Start these evaluations (model API usage may be billed)?", default=False, auto_enter=False))):
            print("Cancelled; configuration was not changed.")
            return 0
    if persist:
        check_config_destination(root, path)
    verify_submission_keys(tasks, env)
    if persist:
        save_env(path, updates)
        print(f"Saved configuration to {path}; API keys are hidden.")
    if args.command == "configure":
        print("Configuration checked. No evaluation started.")
        return 0
    return runner.run_batch(root, tasks, setting, env, pool, concurrency, args.output, args.offline, model_config)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = ["run"]
    command_parser = parser()
    args = command_parser.parse_args(arguments)
    if args.command is None:
        args = command_parser.parse_args([*arguments, "run"])
    try:
        if args.command == "pi-models":
            pi_models.display(args.provider, as_json=args.json)
            return 0
        if args.command == "submission-models":
            if args.json:
                print(json.dumps({"allowed_models": model_ids(args.profile)}, indent=2))
            else:
                display_profile(args.profile)
            return 0
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
        if args.command in ("info", "update"):
            if args.command == "update" and not args.json:
                print(f"Checking upstream updates: {root}", flush=True)
            result = updates.info(root) if args.command == "info" else updates.update(root, check=args.check)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                updates.display(result, checking=args.command == "update" and args.check)
            return 0
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
            path = (args.env_file or root / ".env").expanduser().absolute()
            result = runner.doctor(root, env={**DEFAULTS, **read_env(path), **os.environ})
            print(json.dumps(result, indent=2) if args.json else "\n".join(f"{key}: {value}" for key, value in result.items()))
            return 0
        return configure_run(args, root)
    except KeyboardInterrupt:
        print("Cancelled; inspect the batch summary if execution had started.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
