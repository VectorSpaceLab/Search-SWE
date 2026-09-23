import asyncio
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest

import yaml

from harbor.models.task.config import TaskConfig
from harbor.models.task.verifier_mode import (
    resolve_effective_verifier_env_config,
    resolve_task_verifier_mode,
)
from harbor.models.trial.config import AgentConfig, EnvironmentConfig
from harbor.trial.network_policy import resolve_trial_network_plan

from scripts.harbor_agents import (
    PreinstalledClaudeCode,
    PreinstalledCodex,
    PreinstalledPi,
)
from scripts.run_task import CLAUDE_CODE_EFFORT_LEVELS


REPO = Path(__file__).resolve().parents[2]
TASK_HOSTS = ["openrouter.ai", "api.jina.ai"]
DEEPSEEK_HOST = "api.deepseek.com"
EXPECTED = {
    "task-1-1": ("allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS, "allowlist", [*TASK_HOSTS, DEEPSEEK_HOST]),
    "task-1-2": ("no-network", [], "no-network", [], "allowlist", [DEEPSEEK_HOST]),
    "task-1-3": ("allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS, "allowlist", [*TASK_HOSTS, DEEPSEEK_HOST]),
    "task-1-4": ("allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS, "allowlist", [*TASK_HOSTS, DEEPSEEK_HOST]),
    "task-2-1": ("no-network", [], "no-network", [], "allowlist", [DEEPSEEK_HOST]),
    "task-2-2": ("no-network", [], "no-network", [], "allowlist", [DEEPSEEK_HOST]),
    "task-2-3": ("allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS, "allowlist", [*TASK_HOSTS, DEEPSEEK_HOST]),
    "task-2-4": ("allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS, "allowlist", TASK_HOSTS),
    "task-2-5": ("no-network", [], "no-network", [], "allowlist", [DEEPSEEK_HOST]),
}


class TaskNetworkPolicies(unittest.TestCase):
    @staticmethod
    def _policy_tuple(policy):
        return policy.network_mode.value, policy.allowed_hosts

    def test_harbor_022_resolves_the_expected_phase_policies(self):
        self.assertEqual(
            {path.parent.name for path in (REPO / "tasks").glob("*/task.toml")},
            set(EXPECTED),
        )
        for task_name, expected in EXPECTED.items():
            with self.subTest(task=task_name):
                path = REPO / "tasks" / task_name / "task.toml"
                config = TaskConfig.model_validate_toml(path.read_text())
                plan = resolve_trial_network_plan(
                    config,
                    AgentConfig(),
                    EnvironmentConfig(),
                    None,
                    verifier_mode=resolve_task_verifier_mode(config),
                    env_config=resolve_effective_verifier_env_config(config, None),
                )
                actual = (
                    *self._policy_tuple(plan.agent_env_baseline),
                    *self._policy_tuple(plan.agent_phase),
                    *self._policy_tuple(plan.verifier_phase),
                )
                self.assertEqual(actual, expected)

    def test_allowlists_are_exact_hosts_and_compose_cannot_bypass_sidecar(self):
        for task_name in EXPECTED:
            task = REPO / "tasks" / task_name
            config = tomllib.loads((task / "task.toml").read_text())
            for section in ("environment", "agent", "verifier"):
                policy = config[section]
                hosts = policy.get("allowed_hosts", [])
                self.assertEqual(len(hosts), len(set(hosts)))
                for host in hosts:
                    self.assertNotIn("://", host)
                    self.assertNotIn("*", host)
                    self.assertNotIn("/", host)
            for compose_path in task.glob("*/docker-compose.yaml"):
                compose = yaml.safe_load(compose_path.read_text()) or {}
                for service, service_config in compose.get("services", {}).items():
                    self.assertNotIn(
                        "network_mode", service_config,
                        f"{compose_path}:{service} bypasses Harbor egress control",
                    )
                    self.assertNotIn(
                        "networks", service_config,
                        f"{compose_path}:{service} bypasses Harbor egress control",
                    )

    def test_task_resource_docs_match_the_network_profiles(self):
        for task_name in EXPECTED:
            resource_doc = (
                REPO / "tasks" / task_name / "environment/docs/available_resources.md"
            )
            self.assertTrue(resource_doc.is_file(), task_name)

        for task_name in ("task-1-2", "task-2-1", "task-2-2", "task-2-5"):
            text = (
                REPO / "tasks" / task_name / "environment/docs/available_resources.md"
            ).read_text().lower()
            self.assertTrue("no public network" in text or "network access is disabled" in text or "offline" in text)

        matrix = (REPO / "docs/network-policy.md").read_text()
        for task_name in EXPECTED:
            self.assertIn(f"`{task_name}`", matrix)
        self.assertIn("--allow-agent-host", matrix)
        self.assertIn("Harbor 0.22.0", matrix)

    def test_agent_images_pin_all_preinstalled_clis(self):
        dockerfiles = sorted((REPO / "tasks").glob("*/environment/Dockerfile"))
        self.assertEqual(len(dockerfiles), len(EXPECTED))
        for dockerfile in dockerfiles:
            text = dockerfile.read_text()
            self.assertIn("@openai/codex@${SEARCH_SWE_CODEX_VERSION}", text)
            self.assertIn(
                "@anthropic-ai/claude-code@${SEARCH_SWE_CLAUDE_CODE_VERSION}",
                text,
            )
            self.assertIn("@earendil-works/pi-coding-agent@${SEARCH_SWE_PI_VERSION}", text)
            self.assertIn("SEARCH_SWE_CODEX_VERSION=0.147.0", text)
            self.assertIn("SEARCH_SWE_CLAUDE_CODE_VERSION=2.1.273", text)
            self.assertIn("SEARCH_SWE_PI_VERSION=0.85.1", text)
            claude_install = text.split("&& npm install --global", 1)[1].split(
                "&& codex --version", 1
            )[0]
            self.assertNotIn("--ignore-scripts", claude_install)
            self.assertIn(
                'test "$(claude --version)" = '
                '"${SEARCH_SWE_CLAUDE_CODE_VERSION} (Claude Code)"',
                text,
            )
            self.assertIn(
                'claude --help | grep -F '
                '"(low, medium, high, xhigh, max)" >/dev/null',
                text,
            )

    def test_claude_effort_levels_are_supported_by_the_harbor_adapter(self):
        effort_flag = next(
            flag
            for flag in PreinstalledClaudeCode.CLI_FLAGS
            if flag.kwarg == "reasoning_effort"
        )
        self.assertTrue(set(CLAUDE_CODE_EFFORT_LEVELS) <= set(effort_flag.choices))
        self.assertNotIn("ultracode", CLAUDE_CODE_EFFORT_LEVELS)
        with tempfile.TemporaryDirectory() as directory:
            for effort in CLAUDE_CODE_EFFORT_LEVELS:
                with self.subTest(effort=effort):
                    agent = PreinstalledClaudeCode(
                        logs_dir=Path(directory),
                        model_name="fixture",
                        version="2.1.273",
                        reasoning_effort=effort,
                    )
                    self.assertIn(f"--effort {effort}", agent.build_cli_flags())

    def test_custom_agents_only_check_the_preinstalled_cli(self):
        class FakeEnvironment:
            def __init__(self, output):
                self.output = output
                self.commands = []

            async def exec(self, command, **kwargs):
                self.commands.append((command, kwargs))
                return SimpleNamespace(return_code=0, stdout=self.output)

        cases = (
            (PreinstalledCodex, "0.147.0", "codex-cli 0.147.0\n", "codex --version"),
            (
                PreinstalledClaudeCode,
                "2.1.273",
                "2.1.273 (Claude Code)\n",
                "claude --version",
            ),
            (PreinstalledPi, "0.85.1", "0.85.1\n", "pi --version"),
        )
        for agent_class, version, output, version_command in cases:
            with self.subTest(agent=agent_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    agent = agent_class(
                        logs_dir=Path(directory), model_name="fixture", version=version
                    )
                    environment = FakeEnvironment(output)
                    asyncio.run(agent.setup(environment))
                commands = [command for command, _ in environment.commands]
                self.assertEqual(len(commands), 2)
                self.assertIn("mkdir -p /installed-agent", commands[0])
                self.assertIn(version_command, commands[1])
                self.assertFalse(
                    any(
                        token in command
                        for command in commands
                        for token in ("npm install", "curl", "bootstrap.sh")
                    )
                )

    def test_preinstalled_claude_code_rejects_unsupported_wrong_or_missing_version(self):
        class FakeEnvironment:
            def __init__(self, return_code, output):
                self.return_code = return_code
                self.output = output

            async def exec(self, command, **kwargs):
                return SimpleNamespace(
                    return_code=self.return_code,
                    stdout=self.output,
                )

        with tempfile.TemporaryDirectory() as directory:
            wrong_request = PreinstalledClaudeCode(
                logs_dir=Path(directory),
                model_name="fixture",
                version="2.1.272",
            )
            with self.assertRaisesRegex(
                RuntimeError, "Search-SWE requires Claude Code 2.1.273"
            ):
                asyncio.run(
                    wrong_request.install(FakeEnvironment(0, "2.1.273 (Claude Code)"))
                )

            wrong_installed_cli = PreinstalledClaudeCode(
                logs_dir=Path(directory),
                model_name="fixture",
                version="2.1.273",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "must provide Claude Code 2.1.273; found 2.1.272",
            ):
                asyncio.run(
                    wrong_installed_cli.install(
                        FakeEnvironment(0, "2.1.272 (Claude Code)")
                    )
                )

            missing_cli = PreinstalledClaudeCode(
                logs_dir=Path(directory),
                model_name="fixture",
                version="2.1.273",
            )
            with self.assertRaisesRegex(RuntimeError, "no usable CLI"):
                asyncio.run(missing_cli.install(FakeEnvironment(127, "")))


class LauncherNetworkPolicy(unittest.TestCase):
    def setUp(self):
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                (
                    "AGENT_", "VERIFIER_", "ANSWER_JUDGE_", "CONTAINER_",
                    "DEEPSEEK_API_KEY", "ZAI_API_KEY", "PI_THINKING",
                    "ANTHROPIC_", "CLAUDE_", "AWS_BEARER_TOKEN_BEDROCK",
                )
            )
        }

    def run_preview(self, task, agent, model, values):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            for key, value in values.items():
                env_file.write(f"{key}={value}\n")
            env_path = Path(env_file.name)
        self.addCleanup(env_path.unlink, missing_ok=True)
        return subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/run_task.py"),
                "--task", task,
                "--agent", agent,
                "--model", model,
                "--env-file", str(env_path),
                "--dry-run",
            ],
            cwd=REPO,
            env=self.environment,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def argv(result):
        return shlex.split(result.stdout.splitlines()[-1])

    def test_restricted_agent_phase_gets_only_the_selected_model_host(self):
        cases = (
            ("pi", "deepseek/deepseek-flash", {}, "api.deepseek.com"),
            ("pi", "zai/glm-5.3-flash", {}, "api.z.ai"),
            ("claude-code", "claude-sonnet-4-6", {}, "api.anthropic.com"),
            (
                "codex", "fixture-model",
                {"AGENT_OPENAI_BASE_URL": "https://model.example/v1"},
                "model.example",
            ),
        )
        for agent, model, values, expected_host in cases:
            with self.subTest(agent=agent, model=model):
                result = self.run_preview("task-1-2", agent, model, values)
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = self.argv(result)
                index = argv.index("--allow-agent-host")
                self.assertEqual(argv[index + 1], expected_host)
                expected_import = {
                    "pi": "scripts.harbor_agents:PreinstalledPi",
                    "codex": "scripts.harbor_agents:PreinstalledCodex",
                    "claude-code": "scripts.harbor_agents:PreinstalledClaudeCode",
                }[agent]
                self.assertEqual(argv[argv.index("--agent") + 1], expected_import)

        restricted = self.run_preview("task-2-3", "pi", "deepseek/deepseek-flash", {})
        self.assertEqual(restricted.returncode, 0, restricted.stderr)
        self.assertEqual(
            self.flag_values(self.argv(restricted), "--allow-agent-host"),
            ["api.deepseek.com"],
        )
        restricted = self.run_preview(
            "task-2-3", "claude-code", "claude-sonnet-4-6", {}
        )
        self.assertEqual(restricted.returncode, 0, restricted.stderr)
        self.assertEqual(
            self.flag_values(self.argv(restricted), "--allow-agent-host"),
            ["api.anthropic.com"],
        )

    def test_claude_code_preview_uses_pinned_cli_and_namespaced_key(self):
        secret = "fixture-anthropic-secret"
        result = self.run_preview(
            "task-1-2",
            "claude-code",
            "claude-sonnet-4-6",
            {
                "AGENT_ANTHROPIC_API_KEY": secret,
                "AGENT_REASONING_EFFORT": "xhigh",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        argv = self.argv(result)
        self.assertIn("version=2.1.273", self.flag_values(argv, "--ak"))
        self.assertIn("reasoning_effort=xhigh", self.flag_values(argv, "--ak"))
        self.assertEqual(
            self.flag_values(argv, "--ae"),
            ["ANTHROPIC_API_KEY=${AGENT_ANTHROPIC_API_KEY}"],
        )

    @staticmethod
    def flag_values(argv, flag):
        return [
            argv[index + 1]
            for index, value in enumerate(argv[:-1])
            if value == flag
        ]

    def test_claude_code_rejects_cross_agent_options_and_invalid_effort(self):
        cases = (
            (["--thinking", "high"], "--thinking is only valid"),
            (["--codex-config", "missing.toml"], "--codex-config is only valid"),
            (
                ["--reasoning-effort", "ultracode"],
                "Claude Code reasoning effort must be one of",
            ),
        )
        for options, message in cases:
            with self.subTest(options=options):
                with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
                    env_path = Path(env_file.name)
                self.addCleanup(env_path.unlink, missing_ok=True)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(REPO / "scripts/run_task.py"),
                        "--task",
                        "task-1-2",
                        "--agent",
                        "claude-code",
                        "--model",
                        "claude-sonnet-4-6",
                        "--env-file",
                        str(env_path),
                        *options,
                        "--dry-run",
                    ],
                    cwd=REPO,
                    env=self.environment,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

        result = self.run_preview(
            "task-1-2",
            "claude-code",
            "claude-sonnet-4-6",
            {"AGENT_REASONING_EFFORT": "ultracode"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Claude Code reasoning effort must be one of", result.stderr)

    def test_unlisted_judge_hosts_and_general_proxy_are_rejected(self):
        common = {
            "AGENT_OPENAI_BASE_URL": "https://model.example/v1",
            "VERIFIER_OPENAI_BASE_URL": "https://api.deepseek.com/",
        }
        cases = (
            (
                "task-1-2",
                {**common, "VERIFIER_OPENAI_BASE_URL": "https://relay.example/v1"},
                "not permitted",
            ),
            (
                "task-1-3",
                {**common, "ANSWER_JUDGE_BASE_URL": "https://answer.example/v1"},
                "not permitted",
            ),
            (
                "task-1-2",
                {**common, "CONTAINER_PROXY": "http://proxy.example:8080"},
                "incompatible",
            ),
        )
        for task, values, message in cases:
            with self.subTest(task=task, message=message):
                result = self.run_preview(task, "codex", "fixture-model", values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_task_1_3_accepts_only_its_fixed_judge_hosts(self):
        result = self.run_preview(
            "task-1-3",
            "codex",
            "fixture-model",
            {
                "AGENT_OPENAI_BASE_URL": "https://model.example/v1",
                "VERIFIER_OPENAI_BASE_URL": "https://api.deepseek.com/",
                "ANSWER_JUDGE_BASE_URL": "https://openrouter.ai/api/v1",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
