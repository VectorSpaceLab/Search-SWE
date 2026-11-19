"""Replay a local Harbor trial's recorded artifacts with the checkout's verifier."""

from contextlib import nullcontext
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from uuid import uuid4

from . import runner, updates
from .configuration import DEFAULTS, read_env
from .repository import VARIABLE, check_compatibility, discover
from .resources import Pool, cpu_ids
from .submission_checks import verify_submission_keys


def recorded_trial(source):
    from harbor.models.trial.result import TrialResult

    for name in ("config.json", "result.json", "artifacts/manifest.json"):
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Original Harbor trial is incomplete: missing regular file {path}")
    if (source / "steps").exists():
        raise ValueError("Regrade requires a single-step Harbor trial.")
    try:
        result = TrialResult.model_validate_json((source / "result.json").read_text())
    except ValueError:
        raise ValueError(f"Invalid Harbor trial result: {source / 'result.json'}") from None
    if result.step_results:
        raise ValueError("Regrade requires a single-step Harbor trial.")
    return result


def recorded_inputs(source, task):
    from harbor.constants import MAIN_SERVICE_NAME
    from harbor.models.task.artifacts import convention_source_for_os, effective_artifact_service, with_convention_entry
    from harbor.models.task.config import TaskConfig
    from harbor.trial.artifact_handler import artifact_host_path
    from harbor.trial.regrade import RegradeError, check_task_regradable, read_artifact_manifest

    if problem := check_task_regradable(task):
        raise ValueError(problem)
    if task.name == "large-scale-formula-retrieval":
        raise ValueError(
            f"Regrade is unavailable for {task.name}: its verifier requires the original "
            "agent's private memory evidence at /task-evidence/agent.json, outside the recorded trial."
        )
    config = TaskConfig.model_validate_toml((task / "task.toml").read_text())
    convention = convention_source_for_os(config.environment.os)

    # Harbor copies the two entire trees. Reject links and special files before
    # it can follow links to unrelated host files or block reading a FIFO.
    def walk_error(error):
        raise error

    for directory in (source / "agent", source / "artifacts"):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Original Harbor trial is incomplete: expected directory {directory}")
        for base, directories, files in os.walk(directory, onerror=walk_error):
            for name in directories + files:
                path = Path(base) / name
                mode = path.lstat().st_mode
                if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    raise ValueError(f"Only regular files and directories can be replayed: {path}")

    try:
        manifest = read_artifact_manifest(source)
    except RegradeError:
        raise ValueError(f"Invalid Harbor artifact manifest: {source / 'artifacts/manifest.json'}") from None
    entries = {(item.service or MAIN_SERVICE_NAME, item.source.rstrip("/")): item
               for item in manifest}
    if len(entries) != len(manifest):
        raise ValueError("Original Harbor trial has duplicate manifest entries.")
    missing = []
    for artifact in with_convention_entry(config.artifacts, convention_source=convention):
        key = (effective_artifact_service(artifact), artifact.source.rstrip("/"))
        entry = entries.get(key)
        path = artifact_host_path(source / "artifacts", artifact)
        if entry and entry.destination == path.relative_to(source).as_posix():
            if (entry.status == "empty" and entry.type == "directory"
                    and key == (MAIN_SERVICE_NAME, convention)):
                continue
            if entry.status == "ok" and ((entry.type == "file" and path.is_file())
                                         or (entry.type == "directory" and path.is_dir())):
                continue
        missing.append(artifact.source)
    if missing:
        raise ValueError(f"Original trial is missing usable recorded inputs for {task.name}: "
                         + ", ".join(missing))


def measurement_valid(verifier):
    health = []
    for name in ("reward-details.json", "judge-status.json"):
        try:
            data = json.loads((verifier / name).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        guard = data.get("timeout_guard")
        phase = guard.get("failed_phase") if isinstance(guard, dict) else None
        if isinstance(phase, str) and phase.strip():
            return False
        for details in (data, data.get("final_gate")):
            if not isinstance(details, dict):
                continue
            if type(details.get("measurement_valid")) is bool:
                health.append(details["measurement_valid"])
            elif details.get("evaluation_valid") is True and details.get("judge_succeeded") is False:
                # Some finalizers write zero when the audit could not complete.
                health.append(False)
    return all(health) if health else None


def result_summary(trial, report):
    from harbor.models.trial.result import TrialResult

    try:
        result = TrialResult.model_validate_json((trial / "result.json").read_text())
    except (OSError, ValueError):
        return
    rewards = result.verifier_result.rewards if result.verifier_result else None
    report.update(trial_id=str(result.id), task_checksum=result.task_checksum, rewards=rewards)
    if result.exception_info:
        report.update(measurement_valid=False, status="verifier-error",
                      exception_type=result.exception_info.exception_type)
    elif rewards:
        valid = measurement_valid(trial / "verifier")
        report.update(measurement_valid=valid, status="invalid-measurement" if valid is False else "completed")


def run(args, root):
    from harbor.models.trial.config import AgentConfig, EnvironmentConfig, SourceTrialConfig, TaskConfig, TrialConfig, VerifierConfig

    from harbor.trial.regrade import local_task_name

    check_compatibility(root)
    source = args.trial.expanduser().resolve()
    original = recorded_trial(source)
    name = original.task_name.removeprefix("search-swe/")
    task = discover(root).get(name)
    if task is None:
        raise ValueError(f"Source task {original.task_name!r} is unavailable in this checkout.")
    launcher = runner.backend(root, "evaluation/run_task")
    if not hasattr(launcher, "verifier_settings"):
        raise ValueError("This checkout is missing regrade support. Run search-swe update or select a newer checkout with --repo.")
    task_path = launcher.select_task(root, f"tasks/{name}")
    if original.task_name != local_task_name(task_path):
        raise ValueError(f"Source task {original.task_name!r} does not match the current task metadata.")
    recorded_inputs(source, task_path)

    trial_name = f"{name}__regrade_{uuid4().hex[:12]}"
    output = args.output.expanduser().resolve() if args.output else root / "jobs" / "regrades" / trial_name
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(root / "tasks"):
        raise ValueError(f"Choose a fresh --output outside the source trial and task packages: {output}")
    if args.cpu_set:
        cpu_ids(args.cpu_set)
    if args.gpu_device:
        if task.gpus != 1:
            raise ValueError("--gpu-device requires a single-GPU task.")
        launcher.validate_gpu_device(args.gpu_device)
    env_file = (args.env_file or root / ".env").expanduser().resolve()
    if args.env_file and not env_file.is_file():
        raise ValueError(f"Environment file does not exist: {env_file}")
    env = {**DEFAULTS, **read_env(env_file), **os.environ}
    env = {key: value for key, value in env.items() if value is not None}
    required, verifier_env = launcher.verifier_settings(task.config, env)
    references = {name for value in task.config.get("verifier", {}).get("env", {}).values()
                  for name in VARIABLE.findall(value)}
    required.update(name for name, settings in task.configuration().items()
                    if name in references and settings.get("required"))
    missing = sorted(name for name in required if not env.get(name, "").strip())
    egress_path = root / env["EGRESS_CONFIG"] if env.get("EGRESS_CONFIG") else None
    dns_servers = launcher.parse_servers(env["CONTAINER_DNS"]) if env.get("CONTAINER_DNS") else None
    _, gateway, proxy_env = launcher.network_settings(task_path, env, [], egress_path, dns_servers,
                                                      env.get("EGRESS_IMAGE"))
    if dns_servers and gateway is None:
        raise ValueError("CONTAINER_DNS requires a restricted task or an explicit direct EGRESS_CONFIG")

    print(f"Task: {name}\nSource: {source} ({original.id})\nVerifier checkout: {root}\nOutput: {output}", flush=True)
    if args.dry_run:
        print(f"Verifier resources: {task.cpus} CPUs, {task.memory_mb / 1024:g} GiB RAM, {task.gpus} GPUs.")
        print(f"Preview only. Recorded inputs are present. Missing verifier settings: {', '.join(missing) or 'none'}.")
        return 0
    if missing:
        raise ValueError(f"Set {', '.join(missing)} in {env_file} or the shell.")

    runner.doctor(root, [task], env)
    pool = Pool.host([task], cpu_set=args.cpu_set, gpu_devices=args.gpu_device)
    pool.validate([task], env)
    allocation = pool.acquire(task, env)
    storage = launcher.StoragePlan.discover(task_path, task.config)
    if storage:
        env[storage.cpu_variable] = allocation.cpu_set
    space = runner.backend(root, "assets/asset_space")
    asset_plan = runner.asset_plan(root, [task], env)
    space.describe(asset_plan, root / "tasks")
    space.validate(asset_plan)
    verify_submission_keys([task], env)

    adapter = "PhaseScopedDocker" if gateway is not None else "GpuDocker"
    environment_kwargs = {**(gateway or {}), "cpu_set": allocation.cpu_set}
    if allocation.gpu:
        environment_kwargs["gpu_device"] = allocation.gpu
    config = TrialConfig(
        task=TaskConfig(path=task_path, source=original.source),
        trial_name=trial_name,
        trials_dir=output,
        source_trial=SourceTrialConfig(action="regrade", type="local", trial_id=original.id, path=source),
        agent=AgentConfig(name="nop"),
        environment=EnvironmentConfig(
            import_path=f"scripts.evaluation.harbor_environments:{adapter}",
            override_gpus=0 if task.gpus else None, kwargs=environment_kwargs,
        ),
        verifier=VerifierConfig(env={**verifier_env, **proxy_env}),
    )

    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root), env.get("PYTHONPATH"))))
    git = updates.git_state(root) or {}
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    summary = output / "regrade.json"
    trial = output / trial_name
    report = {
        "task": name, "source_trial": str(source), "source_trial_id": str(original.id),
        "source_task_checksum": original.task_checksum, "trial": str(trial),
        "verifier_checkout": str(root), "verifier_revision": git.get("revision"),
        "verifier_checkout_dirty": git.get("dirty"),
        "measurement_valid": None, "status": "preparing",
    }
    runner.private_json(summary, report)
    try:
        download = [sys.executable, str(root / "scripts/assets/download_assets.py"), "--task", name, "--force"]
        if args.offline:
            download.append("--local-files-only")
        if launcher.run_command(download, env, root):
            raise RuntimeError(f"Asset restoration failed for {name}.")
        launcher.prepare_task(task_path, env, cpu_set=allocation.cpu_set)
        with tempfile.TemporaryDirectory(prefix="search-swe-regrade-") as directory:
            path = Path(directory) / "trial.json"
            runner.private_json(path, config.model_dump(mode="json"))
            report.update(status="verifier-error", measurement_valid=False)
            with launcher.prepared_storage(storage, env) if storage else nullcontext():
                code = launcher.run_command(["harbor", "trial", "start", "--config", str(path)], env, root)
            result_summary(trial, report)
            if code:
                report.update(status="verifier-error", measurement_valid=False, exit_code=code)
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        runner.private_json(summary, report)
        print(f"Regrade summary: {summary} ({report['status']})", flush=True)
    return 0 if report["status"] == "completed" else report.get("exit_code", 1)
