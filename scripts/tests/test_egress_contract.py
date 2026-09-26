"""S0 contracts: real Harbor factory/phase paths, no Docker or model calls.

ContractDocker is a test double, not the proposed production adapter. Only its
constructor uses real DockerEnvironment initialization; start/apply/stop record
events instead of running containers. These tests establish extension seams,
not enforcement correctness.
"""

import asyncio
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from harbor.environments.docker.docker import DockerEnvironment
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig as TaskEnvironment, NetworkPolicy, TaskConfig
from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config, resolve_task_verifier_mode, resolve_step_verifier_mode
from harbor.models.trial.config import AgentConfig, EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from harbor.trial.network_policy import resolve_trial_network_plan
from harbor.trial.trial import Trial

from scripts.tests.egress_s0.fixture import dns_packet, questions
from scripts.tests.egress_s0.run import configuration
from scripts.tests.egress_full_trial import task_config


REPO = Path(__file__).resolve().parents[2]


class ContractDocker(DockerEnvironment):
    instances = []

    def __init__(self, *args, s0_binding=None, **kwargs):
        self.s0_binding = s0_binding
        self.events = []
        self.fail_update = False
        super().__init__(*args, **kwargs)
        self.instances.append(self)

    async def start(self, force_build):
        self.events.append(("start", self.network_policy))

    async def stop(self, delete):
        self.events.append(("stop", delete))

    async def _apply_network_policy(self, policy):
        if self.fail_update:
            raise RuntimeError("fixture policy application failed")
        self.events.append(("policy", policy))


class EgressHarborContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Fixture text-file generation only; no task package is modified.
        (self.root / "Dockerfile").write_text("FROM fixture-not-built\n")
        self.paths = TrialPaths(trial_dir=self.root / "trial")
        patcher = patch.object(DockerEnvironment, "_egress_control_kernel_support", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        ContractDocker.instances.clear()
        self.environment_config = EnvironmentConfig(
            import_path=f"{__name__}:ContractDocker", kwargs={"s0_binding": "host-config-path-only"})

    def create(self, policy):
        return EnvironmentFactory.create_environment_from_config(
            config=self.environment_config, environment_dir=self.root,
            environment_name="s0", session_id="s0-agent", trial_paths=self.paths,
            task_env_config=TaskEnvironment(), network_policy=policy)

    def plan(self, task_name, model_host="model.example"):
        config = TaskConfig.model_validate_toml((REPO / "tasks" / task_name / "task.toml").read_text())
        return resolve_trial_network_plan(
            config, AgentConfig(extra_allowed_hosts=[model_host]), self.environment_config, None,
            verifier_mode=resolve_task_verifier_mode(config),
            env_config=resolve_effective_verifier_env_config(config, None))

    def test_phase_policy_uses_harbor_inheritance_and_model_host_is_agent_only(self):
        plan = self.plan("task-1-1")
        self.assertEqual(plan.agent_env_baseline.allowed_hosts, ["openrouter.ai", "api.jina.ai"])
        self.assertIn("model.example", plan.agent_phase.allowed_hosts)
        self.assertNotIn("model.example", plan.verifier_phase.allowed_hosts)
        self.assertIn("api.deepseek.com", plan.verifier_phase.allowed_hosts)
        self.assertNotIn("api.deepseek.com", plan.agent_phase.allowed_hosts)
        offline = self.plan("task-2-1")
        self.assertEqual(offline.agent_env_baseline.network_mode.value, "no-network")
        self.assertEqual(offline.agent_phase.allowed_hosts, ["model.example"])

    def test_real_separate_verifier_path_preserves_adapter_and_binding_not_overlay(self):
        plan = self.plan("task-1-1")
        agent = self.create(plan.agent_env_baseline)
        external_overlay = self.root / "agent-only.json"
        external_overlay.write_text('{"services": {}}\n')
        self.environment_config.extra_docker_compose = [external_overlay]
        fake_trial = SimpleNamespace(
            config=SimpleNamespace(environment=self.environment_config),
            task=SimpleNamespace(short_name="s0"), paths=self.paths, _id="fixture",
            logger=logging.getLogger("s0"), _environment_build_timeout_sec=5,
            _verifier_env_build_context=lambda step: self.root,
            _separate_verifier_session_id=lambda key: "s0-verifier-" + key,
            _verifier_env_mounts=lambda config: [],
            _validate_separate_verifier_env_policies=lambda env, plan: None)

        async def exercise():
            async with Trial._separate_verifier_env(
                fake_trial, TaskEnvironment(), key="first", plan=plan) as verifier:
                self.assertIsInstance(verifier, ContractDocker)
                self.assertIsNot(verifier, agent)
                self.assertEqual(verifier.s0_binding, "host-config-path-only")
                self.assertEqual(verifier.extra_docker_compose_paths, [])
                self.assertEqual(verifier.network_policy, plan.verifier_env_baseline)
                self.assertEqual(verifier.events[0][0], "start")
            self.assertEqual(verifier.events[-1], ("stop", True))
            async with Trial._separate_verifier_env(
                fake_trial, TaskEnvironment(), key="second", plan=plan) as second:
                self.assertIsNot(second, verifier)

        asyncio.run(exercise())
        self.assertEqual(len(ContractDocker.instances), 3)
        self.assertEqual(self.environment_config.extra_docker_compose, [external_overlay])

    def test_real_phase_context_restores_baseline_on_error(self):
        plan = self.plan("task-1-1")
        environment = self.create(plan.agent_env_baseline)

        async def exercise():
            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                async with Trial._phase_network_policy(
                    None, environment, baseline_policy=plan.agent_env_baseline,
                    phase_policy=plan.agent_phase):
                    self.assertEqual(environment.network_policy, plan.agent_phase)
                    raise RuntimeError("agent failed")

        asyncio.run(exercise())
        self.assertEqual(environment.events, [("policy", plan.agent_phase), ("policy", plan.agent_env_baseline)])
        self.assertEqual(environment.network_policy, plan.agent_env_baseline)

    def test_failed_update_is_not_reported_as_applied(self):
        baseline = NetworkPolicy(network_mode="no-network")
        environment = self.create(baseline)
        environment.fail_update = True
        with self.assertRaisesRegex(RuntimeError, "application failed"):
            asyncio.run(environment.set_network_policy(NetworkPolicy(
                network_mode="allowlist", allowed_hosts=["allowed.example"])))
        self.assertEqual(environment.network_policy, baseline)
        self.assertEqual(environment.events, [])

    def test_dns_fixture_encodes_non_in_and_multiple_questions(self):
        self.assertEqual(questions(dns_packet([("blocked.example", 3)])),
                         [{"name": "blocked.example", "class": 3, "type": 1}])
        self.assertEqual(len(questions(dns_packet([
            ("allowed.example", 1), ("blocked.example", 1)]))), 2)

    def test_candidate_marks_are_strings_for_gost_json_metadata(self):
        # GOST v0.10.9 GetInt does not handle the float64 produced by decoding
        # arbitrary numeric JSON metadata. Losing the mark recurses into red.
        config = configuration("192.0.2.10")
        for service in config["services"]:
            self.assertEqual(service["metadata"]["so_mark"], "114514")
        node = config["chains"][0]["hops"][0]["nodes"][0]
        self.assertEqual(node["metadata"]["so_mark"], "114514")
        self.assertFalse(config["services"][0]["handler"]["metadata"]["sniffing.fallback"])


if __name__ == "__main__":
    unittest.main()


def plans(task, runtime):
    return [resolve_trial_network_plan(task, AgentConfig(extra_allowed_hosts=["model.example"]), runtime, step,
            verifier_mode=resolve_step_verifier_mode(task, step),
            env_config=resolve_effective_verifier_env_config(task, step)) for step in task.steps]


class MultiStepPlansTests(unittest.TestCase):
    def test_step_overrides_do_not_union_with_task_and_model_is_agent_only(self):
        inherited, override, offline, shared = plans(task_config("alpha", "fixture"), EnvironmentConfig())
        self.assertEqual(inherited.agent_env_baseline.allowed_hosts, ["base-alpha.example"])
        self.assertEqual(inherited.agent_phase.allowed_hosts, ["task-alpha.example", "model.example"])
        self.assertEqual(override.agent_phase.allowed_hosts, ["step-alpha.example", "model.example"])
        self.assertEqual(override.verifier_phase.allowed_hosts, ["score-alpha.example"])
        self.assertEqual(override.verifier_env_baseline.network_mode.value, "no-network")
        # Harbor deliberately adds the run's model endpoint to an otherwise
        # offline agent phase. It never adds it to verifier policy.
        self.assertEqual(offline.agent_phase.allowed_hosts, ["model.example"])
        self.assertEqual(offline.verifier_phase.network_mode.value, "no-network")
        self.assertEqual(offline.verifier_env_baseline.allowed_hosts, ["vbase-alpha.example"])
        self.assertIsNone(shared.verifier_env_baseline)
        self.assertEqual(shared.verifier_phase_baseline, inherited.agent_env_baseline)
        self.assertEqual(shared.verifier_phase.allowed_hosts, ["shared-alpha.example"])

    def test_different_task_plans_only_share_explicit_model_host(self):
        a, b = [plans(task_config(name, "fixture"), EnvironmentConfig()) for name in ("alpha", "beta")]
        for first, second in zip(a, b):
            self.assertEqual(set(first.agent_phase.allowed_hosts) & set(second.agent_phase.allowed_hosts), {"model.example"})
            self.assertFalse(set(first.verifier_phase.allowed_hosts) & set(second.verifier_phase.allowed_hosts))

    def test_runtime_environment_hosts_do_not_leak_into_explicit_step_environment(self):
        inherited, override, offline, shared = plans(task_config("alpha", "fixture"),
            EnvironmentConfig(extra_allowed_hosts=["trial-env.example"]))
        self.assertEqual(inherited.agent_env_baseline.allowed_hosts, ["base-alpha.example", "trial-env.example"])
        self.assertEqual(inherited.verifier_env_baseline.allowed_hosts, ["vbase-alpha.example"])
        self.assertEqual(override.verifier_env_baseline.allowed_hosts, [])
        self.assertEqual(override.agent_phase.allowed_hosts, ["step-alpha.example", "model.example"])
        self.assertEqual(offline.verifier_env_baseline.allowed_hosts, ["vbase-alpha.example"])
        self.assertEqual(shared.verifier_phase_baseline.allowed_hosts, ["base-alpha.example", "trial-env.example"])
