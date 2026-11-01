"""Provider coverage and credential isolation without provider requests."""

import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from search_swe import pi_models, wizard
from search_swe.cli import main, parser
from search_swe.configuration import Setting
from scripts.evaluation.harbor_agents import PreinstalledPi
from scripts.evaluation.harness_versions import PI_VERSION
from harbor.agents.installed.pi import Pi


class PiProviderTests(unittest.TestCase):
    def test_pinned_catalog_covers_api_key_chat_models(self):
        data = pi_models.catalog()
        self.assertEqual(data["version"], PI_VERSION)
        self.assertEqual(len(data["providers"]), 40)
        self.assertNotIn("openai-codex", data["providers"])
        self.assertNotIn("typesafe", data["providers"])
        for provider, info in data["providers"].items():
            self.assertIn("apiKey", info["auth"])
            self.assertTrue(info["keys"])
            for model_id in info["models"]:
                full = provider + "/" + model_id
                with self.subTest(model=full):
                    Setting("pi", "direct", full, "default").validate()
                    self.assertTrue(pi_models.agent_host(full, {}, preview=True))

    def test_catalog_command_is_offline_and_needs_no_checkout(self):
        with patch("search_swe.cli.find_repo", side_effect=AssertionError("repo read")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["pi-models", "--provider", "google", "--json"]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["pi_version"], PI_VERSION)
        self.assertTrue(all(row["id"].startswith("google/") for row in data["models"]))

    def test_keys_are_scoped_and_endpoint_settings_are_provider_specific(self):
        examples = {
            "openai": {"AGENT_OPENAI_API_KEY"}, "anthropic": {"AGENT_ANTHROPIC_API_KEY"},
            "openrouter": {"AGENT_OPENROUTER_API_KEY"}, "huggingface": {"AGENT_HF_TOKEN"},
            "google": {"GEMINI_API_KEY"}, "google-vertex": {"GOOGLE_CLOUD_API_KEY"},
            "amazon-bedrock": {"AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION"},
            "azure": {"AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL"},
            "cloudflare-ai-gateway": {"CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_GATEWAY_ID"},
        }
        for provider, expected in examples.items():
            model = provider + "/" + next(iter(pi_models.catalog()["providers"][provider]["models"]))
            self.assertEqual(pi_models.required_variables(model), expected)
        azure = "azure/" + next(iter(pi_models.catalog()["providers"]["azure"]["models"]))
        self.assertEqual(pi_models.required_variables(azure, {"AZURE_OPENAI_RESOURCE_NAME": "example"}),
                         {"AZURE_OPENAI_API_KEY", "AZURE_OPENAI_RESOURCE_NAME"})
        self.assertEqual(pi_models.agent_host(azure, {"AZURE_OPENAI_RESOURCE_NAME": "example"}), "example.openai.azure.com")
        for invalid in ("http://host/v1", "https://secret@host", "https://host/?key=secret"):
            with self.assertRaises(ValueError) as caught:
                pi_models.agent_host(azure, {"AZURE_OPENAI_BASE_URL": invalid})
            self.assertNotIn("secret", str(caught.exception))

    def test_wizard_searches_native_provider_and_only_asks_for_its_key(self):
        model = "google/gemini-2.5-flash"
        with patch.object(wizard, "ask", side_effect=["pi", "direct", "google", model, "default"]), \
                redirect_stdout(io.StringIO()):
            setting = wizard.select_setting(Setting(), parser().parse_args(["configure"]))
        self.assertEqual(setting, Setting("pi", "direct", model, "default"))
        with patch.object(wizard, "ask", return_value="fixture-google"), \
                patch.object(wizard.questionary, "password") as password, redirect_stdout(io.StringIO()):
            env = {"VERIFIER_OPENAI_API_KEY": "fixture-judge", "OPENROUTER_API_KEY": "fixture-submission"}
            updates = {}
            wizard.configure_agent(setting, env, updates)
        self.assertEqual(updates, {"GEMINI_API_KEY": "fixture-google"})
        self.assertEqual(password.call_args.args[0], "GEMINI_API_KEY (required)")

    def test_all_native_providers_generate_minimal_isolated_launcher_config(self):
        values = {"PATH": os.environ["PATH"], "AWS_REGION": "eu-west-1",
                  "AZURE_OPENAI_RESOURCE_NAME": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture",
                  "CLOUDFLARE_GATEWAY_ID": "gateway", "OPENROUTER_API_KEY": "fixture-submission"}
        for provider, info in pi_models.catalog()["providers"].items():
            model = provider + "/" + next(iter(info["models"]))
            with self.subTest(provider=provider):
                env = {**values, **{name: "fixture-provider" for name in pi_models.required_variables(model, values) if name not in values}}
                result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluation/run_task.py"), "--task", "code-context-retrieval",
                                         "--agent", "pi", "--model", model, "--no-env-file", "--dry-run"],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("fixture-provider", result.stdout + result.stderr)
                self.assertNotIn("fixture-submission", result.stdout + result.stderr)
                args = shlex.split(result.stdout.splitlines()[-1])
                actual = [args[i + 1] for i, value in enumerate(args[:-1]) if value == "--ae"]
                expected = [f"{target}=${{{source}}}" for target, source in pi_models.env_bindings(model, env).items()]
                self.assertEqual(actual, expected)
                self.assertEqual(args[args.index("--allow-agent-host") + 1], pi_models.agent_host(model, env))

    def test_adapter_uses_pi_names_and_ignores_host_provider_overrides(self):
        for model, environment in (("google/gemini-2.5-flash", {"GEMINI_API_KEY": "fixture-google"}),
                                   ("openrouter/openai/gpt-6-luna", {"OPENROUTER_API_KEY": "fixture-agent"})):
            with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://wrong.example", "ANTHROPIC_OAUTH_TOKEN": "fixture-oauth"}):
                agent = PreinstalledPi(logs_dir=Path("/tmp"), model_name=model, extra_env=environment)
                connection = agent.model_connection
                self.assertEqual(connection.configured_base_url, None)
                self.assertIsNone(agent._get_env("ANTHROPIC_OAUTH_TOKEN"))
                for key, value in environment.items():
                    self.assertEqual(connection.env[key], value)
                self.assertNotIn("OPENAI_BASE_URL", connection.env)
                self.assertEqual(connection.env["PI_OFFLINE"], "1")
                self.assertIsNone(agent._build_custom_models_json(connection, model.split("/", 1)[1]))

    def test_adapter_preserves_nested_ids_and_quotes_aliases(self):
        agent = PreinstalledPi(logs_dir=Path("/tmp"), model_name="openrouter/~vendor/latest")
        with patch.object(Pi, "exec_as_agent", new_callable=AsyncMock) as execute:
            asyncio.run(agent.exec_as_agent(object(), 'pi --print --mode json --provider openrouter --model ~vendor/latest task'))
        self.assertIn("--model '~vendor/latest'", execute.call_args.args[1])
        for invalid in ("google/model;echo", "google/model$(cmd)", "openai-codex/gpt-6-luna"):
            with self.assertRaises(ValueError):
                Setting("pi", "direct", invalid, "default").validate()

    def test_new_openrouter_model_preserves_capabilities_without_keys_in_config(self):
        metadata = {"id": "vendor/new-model", "name": "New model", "supported_parameters": ["tools", "reasoning"],
                    "endpoints": ["/api/v1/chat/completions"], "input_modalities": ["text", "image"],
                    "context_length": 65536, "max_output_tokens": 8192,
                    "cost": {"input": 1, "output": 2, "cacheRead": 0.1, "cacheWrite": 0}}
        with patch("search_swe.model_catalog.load_models", return_value=({metadata["id"]: metadata}, "cache")) as catalog:
            config = pi_models.resolve_model_config("openrouter/vendor/new-model", offline=True)
        catalog.assert_called_once_with(offline=True, refresh=False)
        agent = PreinstalledPi(logs_dir=Path("/tmp"), model_name="openrouter/vendor/new-model", model_config=config,
                               extra_env={"OPENROUTER_API_KEY": "fixture-agent"})
        with patch("search_swe.model_catalog.load_models", side_effect=AssertionError("runtime metadata request")), \
                patch.object(agent, "exec_as_agent", new_callable=AsyncMock), \
                patch.object(agent, "_upload_config_text", new_callable=AsyncMock) as upload:
            asyncio.run(agent._prepare_model(object()))
        content = upload.call_args.kwargs["content"]
        self.assertNotIn("fixture-agent", content)
        config = json.loads(content)["providers"]["openrouter"]
        self.assertEqual(config["api"], "openai-completions")
        self.assertEqual(config["models"][0], {"id": metadata["id"], "name": "New model", "reasoning": True,
                                             "contextWindow": 65536, "maxTokens": 8192,
                                             "input": ["text", "image"], "cost": metadata["cost"]})

    def test_new_openrouter_model_needs_compatible_metadata_bundled_models_are_offline(self):
        for metadata in ({}, {"vendor/new-model": {"id": "vendor/new-model", "supported_parameters": []}}):
            with patch("search_swe.model_catalog.load_models", return_value=(metadata, "cache")), \
                    self.assertRaisesRegex(ValueError, "compatible catalog metadata"):
                pi_models.resolve_model_config("openrouter/vendor/new-model", offline=True)
        for model in ("deepseek/deepseek-flash", "openrouter/" + next(iter(pi_models.catalog()["providers"]["openrouter"]["models"]))):
            agent = PreinstalledPi(logs_dir=Path("/tmp"), model_name=model)
            with patch("search_swe.model_catalog.load_models", side_effect=AssertionError("Unexpected catalog fetch")):
                self.assertIsNone(pi_models.resolve_model_config(model))
                asyncio.run(agent._prepare_model(object()))

    def test_openrouter_directory_ids_can_be_copied_into_cli(self):
        with redirect_stdout(io.StringIO()) as output:
            pi_models.display("openrouter", as_json=True)
        for row in json.loads(output.getvalue())["models"]:
            Setting("pi", row["provider"], row["id"], "default").validate()
            self.assertEqual(pi_models.native_model(row["id"], row["provider"]), row["native_id"])

    def test_preflight_metadata_reaches_native_launcher_and_adapter_unchanged(self):
        from harbor.cli.utils import parse_kwargs
        from search_swe.runner import launch_command
        from types import SimpleNamespace
        model = {"id": "vendor/new-model", "name": "New", "reasoning": True,
                 "contextWindow": 64000, "maxTokens": 8192, "input": ["text"]}
        setting = Setting("pi", "openrouter", model["id"], "default")
        args = launch_command(ROOT, SimpleNamespace(name="code-context-retrieval"), setting, model_config=model)
        result = subprocess.run([*args, "--dry-run"], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = shlex.split(result.stdout.splitlines()[-1])
        kwargs = parse_kwargs([command[i + 1] for i, value in enumerate(command[:-1]) if value == "--ak"])
        agent = PreinstalledPi(logs_dir=Path("/tmp"), model_name="openrouter/" + model["id"], **kwargs)
        self.assertEqual(agent._model_config, model)
        with self.assertRaisesRegex(ValueError, "does not match"):
            PreinstalledPi(logs_dir=Path("/tmp"), model_name="openrouter/vendor/different", model_config=model)


if __name__ == "__main__":
    unittest.main()
