"""Real Docker adapter/factory smoke, without model calls or task downloads.

Uses no-network except listener-readiness-only phase changes. No API/DNS probes
are sent, and the configured upstream is a reserved TEST-NET address.
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
from types import MethodType, SimpleNamespace
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig as TaskEnvironment, NetworkPolicy, TaskConfig
from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config, resolve_task_verifier_mode
from harbor.models.trial.config import AgentConfig, EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from harbor.trial.network_policy import resolve_trial_network_plan
from harbor.trial.trial import Trial
from scripts.tests.egress_credentials import CredentialProbe


async def cancel_policy(environment, phase, *, queued):
    """Exercise real remote execs, including CLI cancellation before apply."""
    service = "harbor-docker-egress-control-sidecar"
    original = environment._run_docker_compose_command
    applied = asyncio.Event()
    baseline = environment.network_policy
    async def delayed_response(command, *arguments, **keywords):
        if "network-policy" in command and "allow" in command:
            if queued:
                payload = "touch /run/searchswe/cancel-probe; sleep 10; exec " + shlex.join(command[3:])
                return await original(command[:3] + ["sh", "-c", payload], *arguments, **keywords)
            response = await original(command, *arguments, **keywords)
            applied.set()
            await asyncio.Event().wait()
            return response
        return await original(command, *arguments, **keywords)
    environment._run_docker_compose_command = delayed_response
    setter = asyncio.create_task(environment.set_network_policy(phase))
    try:
        if queued:
            for _ in range(20):
                check = await environment.service_exec("test -f /run/searchswe/cancel-probe", service=service)
                if check.return_code == 0:
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError("delayed remote exec did not start")
        else:
            await asyncio.wait_for(applied.wait(), timeout=20)
    finally:
        setter.cancel()
        try:
            await setter
        except asyncio.CancelledError:
            pass
        environment._run_docker_compose_command = original
    state = await original(["ps", "--all", "--format", "json", service])
    rows = [json.loads(line) for line in state.stdout.splitlines() if line.strip()]
    if not rows or any(row["State"] not in {"exited", "dead"} for row in rows):
        raise AssertionError("cancelled setter left the gateway or queued exec running")
    if environment.network_policy != baseline:
        raise AssertionError("cancelled setter updated the cached policy")
    try:
        await environment.set_network_policy(phase)
    except RuntimeError:
        pass
    else:
        raise AssertionError("a terminal control failure was silently recovered")


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = "searchswe-adapter-" + uuid.uuid4().hex[:12]
    environment_dir = output / "environment"
    environment_dir.mkdir()
    (environment_dir / "Dockerfile").write_text(f'FROM python:3.13-slim\nLABEL searchswe.fixture="{session}"\n')
    (environment_dir / "docker-compose.yaml").write_text(json.dumps({"volumes": {"state": {}}, "services": {
        "helper": {"image": args.python_image, "command": ["sleep", "infinity"], "volumes": ["state:/state"]}}}))
    config = output / "egress.json"
    credentials = CredentialProbe(args.auth_file) if args.auth_file or args.credential_probe else None
    upstream = {"url": "http://192.0.2.1:8080"}
    if credentials:
        upstream["auth_file"] = str(credentials.path)
    config.write_text(json.dumps({"version": 1, "image": args.gateway_image,
                                  "upstream": upstream,
                                  "dns": {"doh_url": "https://resolver.example/dns-query"}}))
    agent_overlay = output / "agent-overlay.json"
    agent_overlay.write_text(json.dumps({"services": {"main": {"environment": {"AGENT_ONLY_FIXTURE": "present"}}}}))
    runtime_config = EnvironmentConfig(import_path="scripts.harbor_environments:PhaseScopedDocker",
                                       kwargs={"egress_config": str(config)}, extra_docker_compose=[agent_overlay])
    if credentials:
        credentials.scan(runtime_config.model_dump_json(), "Harbor-environment-job-config")
    baseline = NetworkPolicy(network_mode="no-network")
    phase = NetworkPolicy(network_mode="allowlist", allowed_hosts=["allowed.example"])
    environment = EnvironmentFactory.create_environment_from_config(
        config=runtime_config,
        environment_dir=environment_dir, environment_name=session, session_id=session,
        trial_paths=TrialPaths(trial_dir=output / "trial"),
        task_env_config=TaskEnvironment(docker_image=args.python_image),
        network_policy=baseline, phase_network_policies=[phase])
    result = {"status": "infrastructure_error", "session": session, "checks": []}
    (output / "driver-identity.json").write_text(json.dumps({"session": session, "instance": environment._instance}))
    private = None
    try:
        if not args.orphan_child:
            foreign_volume = session + "_state"
            subprocess.run(["docker", "volume", "create", "--label", f"searchswe.fixture={session}", foreign_volume],
                           check=True, capture_output=True, timeout=30)
            try:
                await environment.start(force_build=False)
            except ValueError as error:
                if "not owned" not in str(error):
                    raise
            else:
                raise AssertionError("foreign named volume was adopted")
            info = json.loads(subprocess.run(["docker", "volume", "inspect", foreign_volume],
                                            check=True, capture_output=True, text=True, timeout=30).stdout)[0]
            if info.get("Labels", {}).get("searchswe.fixture") != session:
                raise AssertionError("foreign-volume positive control lost ownership")
            subprocess.run(["docker", "volume", "rm", foreign_volume], check=True, capture_output=True, timeout=30)
            result["checks"].append({"case": "foreign-volume-rejected-and-not-deleted", "passed": True})
        await environment.start(force_build=args.force_build)
        private = environment._private.name
        if args.orphan_child:
            await environment.set_network_policy(phase)
            if credentials:
                result["checks"].append(await credentials.environment(environment, worker=True))
            (output / "owner-ready.json").write_text(json.dumps({"private": private, "instance": environment._instance,
                                                                 "session": session,
                                                                 "credential_boundary_checked": bool(credentials)}))
            # The dedicated parent test SIGKILLs this process. If the parent
            # disappears instead, normal finally cleanup runs after this bound.
            await asyncio.sleep(180)
            raise RuntimeError("orphan fixture was not interrupted")
        rendered = await environment._run_docker_compose_command(["config", "--format", "json"])
        (output / "compose.json").write_text(rendered.stdout)
        script = """import json,os,socket
from pathlib import Path
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert int(status['CapBnd'].strip(),16)&((1<<12)|(1<<13))==0
assert not Path('/opt/searchswe/input.json').exists()
assert not Path('/run/searchswe/control.sock').exists()
sock=socket.socket()
try:
 sock.setsockopt(socket.SOL_SOCKET,36,114514)
except PermissionError:
 print(json.dumps({'uid':os.getuid(),'mark_denied':True,'agent_fixture':os.environ.get('AGENT_ONLY_FIXTURE')}))
else:
 raise AssertionError('mark unexpectedly permitted')
"""
        for service in ("main", "helper"):
            response = await environment.service_exec("python -c " + shlex.quote(script), service=service)
            if response.return_code:
                raise RuntimeError(f"capability probe failed: {service}")
            if service == "main" and json.loads(response.stdout)["agent_fixture"] != "present":
                raise RuntimeError("agent-only overlay positive control failed")
            result["checks"].append({"service": service, "result": json.loads(response.stdout)})
        try:
            async with Trial._phase_network_policy(None, environment, baseline_policy=baseline, phase_policy=phase):
                if environment.network_policy != phase:
                    raise AssertionError("phase not applied")
                if credentials:
                    result["checks"].append(await credentials.environment(environment, worker=True))
                raise RuntimeError("intentional fixture exception")
        except RuntimeError as error:
            if str(error) != "intentional fixture exception":
                raise
        if environment.network_policy != baseline:
            raise AssertionError("baseline not restored")
        result["checks"].append({"case": "real-phase-exception-restores-baseline", "passed": True})
        repo = Path(__file__).resolve().parents[2]
        task_config = TaskConfig.model_validate_toml((repo / "tasks/task-1-1/task.toml").read_text())
        plan = resolve_trial_network_plan(task_config, AgentConfig(extra_allowed_hosts=["model.example"]),
                                          runtime_config, None, verifier_mode=resolve_task_verifier_mode(task_config),
                                          env_config=resolve_effective_verifier_env_config(task_config, None))
        trial = SimpleNamespace(config=SimpleNamespace(environment=runtime_config),
                                task=SimpleNamespace(short_name=session), paths=environment.trial_paths, _id=session,
                                logger=logging.getLogger(session), _environment_build_timeout_sec=180,
                                _verifier_env_build_context=lambda step: environment_dir,
                                _separate_verifier_session_id=lambda key: session + "-verifier-" + key,
                                _verifier_env_mounts=lambda config: [])
        trial._validate_dynamic_phase_switch = MethodType(Trial._validate_dynamic_phase_switch, trial)
        trial._validate_separate_verifier_env_policies = MethodType(Trial._validate_separate_verifier_env_policies, trial)
        private_paths = {private}
        for key in ("first", "second"):
            async with Trial._separate_verifier_env(trial, TaskEnvironment(docker_image=args.python_image),
                                                     key=key, plan=plan) as verifier:
                if type(verifier) is not type(environment) or verifier.extra_docker_compose_paths:
                    raise AssertionError("independent verifier adapter/config was not preserved")
                if verifier._private.name in private_paths:
                    raise AssertionError("private gateway instance was reused")
                private_paths.add(verifier._private.name)
                response = await verifier.exec("test -z \"$AGENT_ONLY_FIXTURE\"")
                if response.return_code:
                    raise AssertionError("agent-only overlay leaked into verifier")
                async with Trial._phase_network_policy(None, verifier, baseline_policy=plan.verifier_env_baseline,
                                                        phase_policy=plan.verifier_phase):
                    if "model.example" in verifier.network_policy.allowed_hosts:
                        raise AssertionError("agent model host leaked into verifier")
                    response = await verifier.exec("python -c " + shlex.quote(script))
                    if response.return_code:
                        raise AssertionError("verifier capability/private mount probe failed")
                    if credentials:
                        result["checks"].append(await credentials.environment(verifier, worker=True))
                if key == "second":
                    await cancel_policy(verifier, phase, queued=True)
                    result["checks"].append({"case": "cancel-before-queued-apply-kills-remote-exec", "passed": True})
            if verifier._private is not None:
                raise AssertionError("independent verifier cleanup did not complete")
            result["checks"].append({"case": "independent-verifier-" + key, "passed": True})
        await asyncio.gather(environment.set_network_policy(phase), environment.set_network_policy(baseline))
        state = await environment._run_docker_compose_command(
            ["exec", "--no-TTY", "harbor-docker-egress-control-sidecar", "network-policy", "show"])
        if environment.network_policy != baseline or json.loads(state.stdout).get("mode") != "no-network":
            raise AssertionError("concurrent setters were not serialized")
        result["checks"].append({"case": "concurrent-setters-serialized", "passed": True})

        await cancel_policy(environment, phase, queued=False)
        result["checks"].append({"case": "cancel-after-apply-kills-before-return", "passed": True})
        result["status"] = "passed"
    except Exception as error:
        result["error"] = str(error)
    finally:
        try:
            await environment.stop(delete=True)
            result["private_directory_removed"] = private is None or not Path(private).exists()
            if args.force_build:
                # Harbor image IDs are content-based, not session-based. The
                # unique fixture label above makes this tag exclusively ours.
                inspected = subprocess.run(["docker", "image", "inspect", environment._main_image_name],
                                           capture_output=True, text=True, timeout=30)
                if inspected.returncode == 0:
                    labels = json.loads(inspected.stdout)[0]["Config"].get("Labels", {})
                    if labels.get("searchswe.fixture") != session:
                        raise RuntimeError("fixture image ownership mismatch")
                    subprocess.run(["docker", "image", "rm", environment._main_image_name],
                                   capture_output=True, text=True, check=True, timeout=30)
                elif "No such image" not in inspected.stderr:
                    raise RuntimeError("could not verify fixture image cleanup")
                result["fixture_image_tag_removed"] = True
        except Exception as error:
            result["status"] = "cleanup_error"
            result["cleanup_error"] = str(error)
        if credentials:
            try:
                credentials.artifacts(output)
                credentials.scan(json.dumps(result), "final-result")
                result["checks"].append({"case": "credential-artifacts-and-audits-clean", "passed": True})
            except Exception:
                result = {"status": "credential_evidence_error", "error": "Credential evidence validation failed; inspect withheld-file notices"}
            finally:
                credentials.close()
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--python-image", default="python:3.13-slim")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force-build", action="store_true", help="Also exercise the launcher's task image build path")
    credentials = parser.add_mutually_exclusive_group()
    credentials.add_argument("--credential-probe", action="store_true", help="Use synthetic credentials and inspect all service boundaries")
    credentials.add_argument("--auth-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--orphan-child", action="store_true", help=argparse.SUPPRESS)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
