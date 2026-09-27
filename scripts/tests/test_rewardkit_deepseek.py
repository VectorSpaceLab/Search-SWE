import asyncio
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
REWARDKIT_TASKS = {
    "task-1-1",
    "task-1-2",
    "task-1-3",
    "task-1-4",
    "task-2-1",
    "task-2-2",
    "task-2-3",
    "task-2-5",
}


def installed_rewardkit_version():
    try:
        return importlib.metadata.version("harbor-rewardkit")
    except importlib.metadata.PackageNotFoundError:
        return None


class RewardKitDeepSeekConfiguration(unittest.TestCase):
    def test_every_rewardkit_task_uses_one_fixed_version_and_model(self):
        discovered = {
            path.parents[2].name
            for path in (REPO / "tasks").glob("*/tests/jailbreak_judge/codex.toml")
        }
        self.assertEqual(discovered, REWARDKIT_TASKS)

        wrapper_bytes = None
        for task_name in sorted(REWARDKIT_TASKS):
            with self.subTest(task=task_name):
                tests = REPO / "tasks" / task_name / "tests"
                rubric = tomllib.loads(
                    (tests / "jailbreak_judge/codex.toml").read_text()
                )
                self.assertEqual(rubric["judge"]["judge"], "deepseek-codex")
                self.assertEqual(rubric["judge"]["model"], "deepseek-flash")

                dockerfile = (tests / "Dockerfile").read_text()
                self.assertIn('"harbor-rewardkit==0.2.0"', dockerfile)
                self.assertIn('"litellm==1.97.0"', dockerfile)
                self.assertIn("REWARDKIT_CODEX_VERSION=0.147.0", dockerfile)
                self.assertIn("@openai/codex@${REWARDKIT_CODEX_VERSION}", dockerfile)
                self.assertIn("registry.npmmirror.com", dockerfile)
                self.assertNotIn("harbor-rewardkit==0.1", dockerfile)

                script = (tests / "test.sh").read_text()
                self.assertIn("/tests/rewardkit_deepseek.py", script)
                self.assertIn("--judge deepseek-codex", script)
                self.assertIn("--model deepseek-flash", script)
                self.assertNotIn("/opt/conda/bin/rewardkit", script)
                self.assertNotIn("CODEX_HOME=", script)

                wrapper = (tests / "rewardkit_deepseek.py").read_bytes()
                if wrapper_bytes is None:
                    wrapper_bytes = wrapper
                self.assertEqual(wrapper, wrapper_bytes)

                task = tomllib.loads(
                    (REPO / "tasks" / task_name / "task.toml").read_text()
                )
                verifier = task["verifier"]["env"]
                environment = task["environment"].get("env", {})
                self.assertNotIn("OPENAI_BASE_URL", environment)
                self.assertNotIn("OPENAI_API_KEY", environment)
                self.assertNotIn("VERIFIER_OPENAI_BASE_URL", environment)
                self.assertNotIn("VERIFIER_OPENAI_API_KEY", environment)
                self.assertEqual(
                    verifier["OPENAI_BASE_URL"],
                    "${VERIFIER_OPENAI_BASE_URL:-}",
                )
                self.assertEqual(
                    verifier["OPENAI_API_KEY"],
                    "${VERIFIER_OPENAI_API_KEY:-}",
                )

        # Every verifier that executes candidate code starts it from an empty
        # environment, then adds only task-approved variables. Task 2-2 loads a
        # constrained local checkpoint and does not execute a submission script.
        credential_boundaries = (
            "tasks/task-1-1/tests/grader.py",
            "tasks/task-1-2/tests/grader.py",
            "tasks/task-1-3/tests/test.sh",
            "tasks/task-1-4/tests/test.sh",
            "tasks/task-2-1/tests/grader.py",
            "tasks/task-2-3/tests/run_evaluation.sh",
            "tasks/task-2-5/tests/test.sh",
        )
        for relative in credential_boundaries:
            with self.subTest(credential_boundary=relative):
                text = (REPO / relative).read_text()
                self.assertIn("/usr/bin/env", text)
                self.assertIn("-i", text)
                self.assertNotIn("DEEPSEEK_API_KEY", text)

        query_runner = (REPO / "tasks/task-1-3/tests/run_queries.py").read_text()
        self.assertIn("env=submission_env()", query_runner)
        self.assertNotIn("DEEPSEEK_API_KEY", query_runner)

    def test_task_without_agent_judge_has_no_rewardkit_integration(self):
        tests = REPO / "tasks/task-2-4/tests"
        self.assertFalse((tests / "jailbreak_judge/codex.toml").exists())
        self.assertFalse((tests / "rewardkit_deepseek.py").exists())
        self.assertNotIn("rewardkit", (tests / "Dockerfile").read_text().lower())

    def test_documented_endpoint_and_version_match_implementation(self):
        example = (REPO / ".env.example").read_text()
        evaluation = (REPO / "docs/evaluation.md").read_text()
        for text in (example, evaluation):
            self.assertIn(
                "VERIFIER_OPENAI_BASE_URL=https://api.deepseek.com/", text
            )
            self.assertIn("0.2.0", text)
        self.assertIn("deepseek-flash", evaluation)
        self.assertIn("env_key = \"DEEPSEEK_API_KEY\"", evaluation)
        self.assertIn("api-docs.deepseek.com", evaluation)

    def test_environment_template_lists_every_user_supplied_api_key(self):
        example = (REPO / ".env.example").read_text()
        assignments = dict(
            line.split("=", 1)
            for line in example.splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        expected_api_keys = {
            "DEEPSEEK_API_KEY",
            "ZAI_API_KEY",
            "AGENT_OPENAI_API_KEY",
            "AGENT_ANTHROPIC_API_KEY",
            "AGENT_OPENROUTER_API_KEY",
            "VERIFIER_OPENAI_API_KEY",
            "ANSWER_JUDGE_API_KEY",
            "TASK_1_1_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "JINA_API_KEY",
        }
        self.assertEqual(
            {name for name in assignments if name.endswith("API_KEY")},
            expected_api_keys,
        )
        for name in expected_api_keys:
            self.assertEqual(assignments[name], "", f"{name} must be an empty placeholder")

        for readme in ("README.md", "README_zh.md"):
            text = (REPO / readme).read_text()
            for name in (
                "DEEPSEEK_API_KEY",
                "ZAI_API_KEY",
                "AGENT_OPENAI_API_KEY",
                "AGENT_ANTHROPIC_API_KEY",
                "AGENT_OPENROUTER_API_KEY",
                "VERIFIER_OPENAI_API_KEY",
                "ANSWER_JUDGE_*",
                "OPENROUTER_API_KEY",
                "JINA_API_KEY",
            ):
                self.assertIn(name, text, f"{readme} does not explain {name}")

    @unittest.skipUnless(
        installed_rewardkit_version() == "0.2.0",
        "harbor-rewardkit 0.2.0 is not installed in this test environment",
    )
    def test_generated_codex_config_is_valid_and_contains_no_key(self):
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        path = REPO / "tasks/task-1-1/tests/rewardkit_deepseek.py"
        spec = importlib.util.spec_from_file_location("rewardkit_deepseek_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with mock.patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "https://api.deepseek.com///"},
        ):
            self.assertEqual(module.deepseek_base_url(), "https://api.deepseek.com")
        for invalid in (
            "",
            "api.deepseek.com",
            "ftp://api.deepseek.com",
            "https://user:secret@api.deepseek.com",
            "https://api.deepseek.com?token=secret",
            "https://api.deepseek.com/#fragment",
        ):
            with self.subTest(invalid_base_url=invalid):
                with mock.patch.dict(
                    os.environ, {"OPENAI_BASE_URL": invalid}, clear=False
                ):
                    with self.assertRaises(ValueError):
                        module.deepseek_base_url()

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "config.toml").write_text(
                '[mcp_servers.fixture]\ncommand = "true"\n', encoding="utf-8"
            )
            module.configure_codex_home(home, "https://api.deepseek.com")
            config_text = (home / "config.toml").read_text()
            config = tomllib.loads(config_text)
            catalog = json.loads((home / "models.json").read_text())

        provider = config["model_providers"]["deepseek"]
        self.assertEqual(config["model_provider"], "deepseek")
        self.assertEqual(provider["base_url"], "https://api.deepseek.com")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(provider["env_key"], "DEEPSEEK_API_KEY")
        self.assertEqual(catalog["models"][0]["slug"], "deepseek-flash")
        self.assertIn("fixture", config["mcp_servers"])
        self.assertNotIn("OPENAI_API_KEY=", config_text)

    @unittest.skipUnless(
        installed_rewardkit_version() == "0.2.0",
        "harbor-rewardkit 0.2.0 is not installed in this test environment",
    )
    def test_backend_maps_key_and_cleans_temporary_home_on_failure(self):
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        path = REPO / "tasks/task-1-1/tests/rewardkit_deepseek.py"
        spec = importlib.util.spec_from_file_location(
            "rewardkit_deepseek_lifecycle_test", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from rewardkit.agents import CodexBackend
        from rewardkit.models import AgentJudge

        homes = []

        async def fake_codex_enter(backend):
            backend._temp_dir = tempfile.TemporaryDirectory()
            backend.codex_home = Path(backend._temp_dir.name)
            backend.binary = Path("/fixture/codex")
            backend.env = {"CODEX_API_KEY": "judge-secret"}
            homes.append(backend.codex_home)
            return backend

        with mock.patch.object(CodexBackend, "__aenter__", fake_codex_enter):
            with mock.patch.dict(
                os.environ,
                {"OPENAI_BASE_URL": "https://api.deepseek.com/"},
            ):
                good = module.DeepSeekCodexBackend(
                    AgentJudge(agent="deepseek-codex", model="deepseek-flash"),
                    None,
                )
                asyncio.run(good.__aenter__())
                self.assertEqual(good.env["DEEPSEEK_API_KEY"], "judge-secret")
                self.assertNotIn("CODEX_API_KEY", good.env)
                self.assertNotIn(
                    "judge-secret", (good.codex_home / "config.toml").read_text()
                )
                asyncio.run(good.__aexit__(None, None, None))

                bad = module.DeepSeekCodexBackend(
                    AgentJudge(agent="deepseek-codex", model="not-deepseek"),
                    None,
                )
                with self.assertRaisesRegex(ValueError, "must be deepseek-flash"):
                    asyncio.run(bad.__aenter__())

        self.assertEqual(len(homes), 2)
        self.assertTrue(all(not home.exists() for home in homes))
        self.assertIsNone(bad.codex_home)
        self.assertIsNone(bad.binary)
        self.assertIsNone(bad.env)


if __name__ == "__main__":
    unittest.main()
