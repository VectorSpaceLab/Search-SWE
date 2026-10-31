import asyncio
import ast
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


def installed_rewardkit_version():
    try:
        return importlib.metadata.version("harbor-rewardkit")
    except importlib.metadata.PackageNotFoundError:
        return None


class RewardKitDeepSeekConfiguration(unittest.TestCase):
    def test_every_rewardkit_task_uses_one_fixed_version_and_model(self):
        tasks = sorted(path.parents[2] for path in (REPO / "tasks").glob("*/tests/jailbreak_judge/codex.toml"))
        self.assertTrue(tasks)
        wrapper_bytes = None
        for task_path in tasks:
            with self.subTest(task=task_path.name):
                tests = task_path / "tests"
                rubric = tomllib.loads(
                    (tests / "jailbreak_judge/codex.toml").read_text()
                )
                self.assertEqual(rubric["judge"]["judge"], "deepseek-codex")
                self.assertEqual(rubric["judge"]["model"], "deepseek/deepseek-v4.1-flash")

                dockerfile = (tests / "Dockerfile").read_text()
                self.assertIn('"harbor-rewardkit==0.2.0"', dockerfile)
                self.assertIn('"litellm==1.97.0"', dockerfile)
                self.assertIn("REWARDKIT_CODEX_VERSION=0.164.0", dockerfile)
                self.assertIn("@openai/codex@${REWARDKIT_CODEX_VERSION}", dockerfile)
                self.assertIn("registry.npmmirror.com", dockerfile)
                self.assertNotIn("harbor-rewardkit==0.1", dockerfile)

                script = (tests / "test.sh").read_text()
                if (tests / "trajectory_gate.py").is_file():
                    self.assertIn("/tests/trajectory_gate.py", script)
                    gate = (tests / "trajectory_gate.py").read_text()
                    self.assertIn('"rewardkit_deepseek.py"', gate)
                    self.assertIn('"deepseek-codex"', gate)
                    self.assertIn('"deepseek/deepseek-v4.1-flash"', gate)
                else:
                    self.assertIn("/tests/rewardkit_deepseek.py", script)
                    self.assertIn("--judge deepseek-codex", script)
                    self.assertIn("--model deepseek/deepseek-v4.1-flash", script)
                self.assertNotIn("/opt/conda/bin/rewardkit", script)
                self.assertNotIn("CODEX_HOME=", script)

                wrapper = (tests / "rewardkit_deepseek.py").read_bytes()
                tree = ast.parse(wrapper)
                codex_version = next(node.value.value for node in tree.body
                                     if isinstance(node, ast.Assign)
                                     and any(isinstance(target, ast.Name) and target.id == "CODEX_VERSION"
                                             for target in node.targets))
                self.assertIn(f"REWARDKIT_CODEX_VERSION={codex_version}", dockerfile)
                if wrapper_bytes is None:
                    wrapper_bytes = wrapper
                self.assertEqual(wrapper, wrapper_bytes)

                task = tomllib.loads(
                    (task_path / "task.toml").read_text()
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
        # environment, then adds only task-approved variables. Task code-embedding-finetuning loads a
        # constrained local checkpoint and does not execute a submission script.
        credential_boundaries = (
            "tasks/reasoning-query-rewriting/tests/grader.py",
            "tasks/memory-constrained-dense-retrieval/tests/grader.py",
            "tasks/scientific-paper-qa/tests/test.sh",
            "tasks/long-pdf-evidence/tests/test.sh",
            "tasks/long-document-reranking/tests/grader.py",
            "tasks/query-encoder-alignment/tests/run_evaluation.sh",
            "tasks/sparse-retrieval-pruning/tests/test.sh",
        )
        for relative in credential_boundaries:
            with self.subTest(credential_boundary=relative):
                text = (REPO / relative).read_text()
                self.assertIn("/usr/bin/env", text)
                self.assertIn("-i", text)
                self.assertNotIn("DEEPSEEK_API_KEY", text)

        query_runner = (REPO / "tasks/scientific-paper-qa/tests/run_queries.py").read_text()
        self.assertIn("env=submission_env()", query_runner)
        self.assertNotIn("DEEPSEEK_API_KEY", query_runner)

    def test_documented_endpoint_and_version_match_implementation(self):
        example = (REPO / ".env.example").read_text()
        evaluation = (REPO / "docs/evaluation.md").read_text()
        for text in (example, evaluation):
            self.assertIn(
                "VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1", text
            )
            self.assertIn("0.2.0", text)
        self.assertIn("deepseek/deepseek-v4.1-flash", evaluation)
        self.assertIn("env_key = \"OPENROUTER_API_KEY\"", evaluation)
        self.assertIn("openrouter.ai/docs", evaluation)

    def test_environment_template_documents_common_credentials_without_secrets(self):
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
            "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "JINA_API_KEY",
        }
        self.assertTrue(expected_api_keys <= assignments.keys())
        for name in assignments:
            if not name.endswith("API_KEY"):
                continue
            self.assertEqual(assignments[name], "", f"{name} must be an empty placeholder")

        for readme in ("README.md", "README_zh.md"):
            text = (REPO / readme).read_text()
            self.assertIn("(docs/evaluation.md)", text, f"{readme} must link to credential setup")
        guide = (REPO / "docs/evaluation.md").read_text()
        for name in (
            "DEEPSEEK_API_KEY",
            "ZAI_API_KEY",
            "AGENT_OPENAI_API_KEY",
            "AGENT_ANTHROPIC_API_KEY",
            "AGENT_OPENROUTER_API_KEY",
            "VERIFIER_OPENAI_API_KEY",
            "ANSWER_JUDGE_MODEL_NAME",
            "ANSWER_JUDGE_BASE_URL",
            "ANSWER_JUDGE_API_KEY",
            "OPENROUTER_API_KEY",
            "JINA_API_KEY",
        ):
            self.assertIn(name, guide, f"docs/evaluation.md does not explain {name}")

    @unittest.skipUnless(
        installed_rewardkit_version() == "0.2.0",
        "harbor-rewardkit 0.2.0 is not installed in this test environment",
    )
    def test_generated_codex_config_is_valid_and_contains_no_key(self):
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        path = REPO / "tasks/reasoning-query-rewriting/tests/rewardkit_deepseek.py"
        spec = importlib.util.spec_from_file_location("rewardkit_deepseek_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from rewardkit import agents
        self.assertEqual(agents._CODEX_VERSION, module.CODEX_VERSION)
        self.assertEqual(agents._codex_cache_dir().name, module.CODEX_VERSION)

        with mock.patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1///"},
        ):
            self.assertEqual(module.deepseek_base_url(), "https://openrouter.ai/api/v1")
        for invalid in (
            "",
            "api.deepseek.com",
            "ftp://api.deepseek.com",
            "https://api.deepseek.com",
            "https://openrouter.ai/api/v1/other",
            "https://user:secret@api.deepseek.com",
            "https://openrouter.ai/api/v1?token=secret",
            "https://openrouter.ai/api/v1/#fragment",
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
            module.configure_codex_home(home, "https://openrouter.ai/api/v1")
            config_text = (home / "config.toml").read_text()
            config = tomllib.loads(config_text)
            catalog = json.loads((home / "models.json").read_text())

        provider = config["model_providers"]["openrouter"]
        self.assertEqual(config["model_provider"], "openrouter")
        self.assertEqual(provider["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(provider["env_key"], "OPENROUTER_API_KEY")
        self.assertEqual(catalog["models"][0]["slug"], "deepseek/deepseek-v4.1-flash")
        self.assertIn("fixture", config["mcp_servers"])
        self.assertNotIn("OPENAI_API_KEY=", config_text)

    @unittest.skipUnless(
        installed_rewardkit_version() == "0.2.0",
        "harbor-rewardkit 0.2.0 is not installed in this test environment",
    )
    def test_backend_maps_key_and_cleans_temporary_home_on_failure(self):
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        path = REPO / "tasks/reasoning-query-rewriting/tests/rewardkit_deepseek.py"
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
                {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1/"},
            ):
                good = module.DeepSeekCodexBackend(
                    AgentJudge(agent="deepseek-codex", model="deepseek/deepseek-v4.1-flash"),
                    None,
                )
                asyncio.run(good.__aenter__())
                self.assertEqual(good.env["OPENROUTER_API_KEY"], "judge-secret")
                self.assertNotIn("CODEX_API_KEY", good.env)
                self.assertNotIn(
                    "judge-secret", (good.codex_home / "config.toml").read_text()
                )
                asyncio.run(good.__aexit__(None, None, None))

                bad = module.DeepSeekCodexBackend(
                    AgentJudge(agent="deepseek-codex", model="not-deepseek"),
                    None,
                )
                with self.assertRaisesRegex(ValueError, "must be deepseek/deepseek-v4.1-flash"):
                    asyncio.run(bad.__aenter__())

        self.assertEqual(len(homes), 2)
        self.assertTrue(all(not home.exists() for home in homes))
        self.assertIsNone(bad.codex_home)
        self.assertIsNone(bad.binary)
        self.assertIsNone(bad.env)


if __name__ == "__main__":
    unittest.main()
