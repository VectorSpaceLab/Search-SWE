"""Check managed harness setup/cache in real Docker without model API calls.

Run from the checkout root with the Search-SWE Python environment.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from harbor.models.task.config import EnvironmentConfig, NetworkPolicy
from harbor.models.trial.paths import TrialPaths
from scripts.evaluation.harbor_environments import PhaseScopedDocker
from scripts.evaluation.native_agents import NativeAgent
from scripts.evaluation.harbor_agents import ManagedCodex, ManagedClaudeCode, ManagedPi
from search_swe import harbor_native, harnesses


async def check(args):
    work = args.output.expanduser().resolve()
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.environ["SEARCH_SWE_HARNESS_CACHE"] = str(work / "cache")
    directory = work / "environment"
    directory.mkdir()
    image = "hanhainebula/search-swe-base:cpu-py3.12-1.0.0"
    (directory / "Dockerfile").write_text(f"FROM {image}\n")
    (directory / "docker-compose.yaml").write_text("services:\n  main: {}\n")
    records = []
    for name in args.agents:
        for attempt in range(2):
            paths = TrialPaths(work / f"{name}-{attempt}")
            paths.mkdir()
            policy = NetworkPolicy(network_mode="no-network")
            environment = PhaseScopedDocker(
                environment_dir=directory, environment_name="harness-install-check",
                session_id="harnesscheck-" + uuid.uuid4().hex[:10], trial_paths=paths,
                task_env_config=EnvironmentConfig(docker_image=image, cpus=1, memory_mb=2048,
                                                 storage_mb=8192, workdir="/app"),
                network_policy=policy, egress_config=str(args.egress_config) if args.egress_config else None)
            classes = {"codex": ManagedCodex, "claude-code": ManagedClaudeCode, "pi": ManagedPi}
            model = "gemini/gemini-2.5-flash" if name in ("gemini-cli", "antigravity-cli") else "openai/gpt-6-luna"
            version = {"version": args.agent_version} if args.agent_version else {}
            agent = (classes[name](logs_dir=paths.agent_dir, model_name=model, **version) if name in classes else
                     NativeAgent(search_swe_native_name=name, logs_dir=paths.agent_dir, model_name=model,
                                 search_swe_setup_hosts=harbor_native.plan(name, model, {})["setup_hosts"], **version))
            try:
                await asyncio.wait_for(environment.start(force_build=False), timeout=120)
                await asyncio.wait_for(agent.setup(environment), timeout=900)
                assert environment.network_policy == policy, "Setup retained distribution access"
                if name == "codex":
                    patch = "*** Begin Patch\n*** Add File: /tmp/managed-patch-check\n+ready\n*** End Patch\n"
                    command = "printf %s " + shlex.quote(patch) + " | apply_patch && test \"$(cat /tmp/managed-patch-check)\" = ready"
                    probe = await environment.exec(command, user="65534", timeout_sec=20)
                    assert probe.return_code == 0, probe.stderr
                record = json.loads((paths.agent_dir / "harness.json").read_text())
                assert record["cache_hit"] == bool(attempt), record
                assert record["actual_version"] == (args.agent_version or harnesses.default_version(name)).removeprefix("v")
                denied = await environment.exec("curl --connect-timeout 3 --max-time 5 -I https://registry.npmjs.org", timeout_sec=10)
                assert denied.return_code != 0, "Task network restriction was not restored"
                record.update(attempt=attempt, post_install_network_restored=True, inference_calls=0)
                records.append(record)
                (work / "results.json").write_text(json.dumps(records, indent=2) + "\n")
                print(json.dumps(record), flush=True)
            finally:
                await environment.stop(delete=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh evidence/cache directory")
    parser.add_argument("--agents", nargs="+", choices=sorted(harnesses.registry()["agents"]), default=["codex"])
    parser.add_argument("--agent-version", type=harnesses.version_argument, help="Exact version; use with one harness")
    parser.add_argument("--egress-config", type=Path, help="Host's working restricted-egress JSON")
    args = parser.parse_args()
    if args.agent_version and (len(args.agents) != 1 or args.agent_version == "default"):
        parser.error("--agent-version requires one harness and an exact version")
    asyncio.run(check(args))


if __name__ == "__main__":
    main()
