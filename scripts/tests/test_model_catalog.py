from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prompt_toolkit.document import Document
from search_swe.cli import parser
from search_swe.configuration import Setting
from search_swe.model_catalog import ModelCompleter, eligible, load_models, parse_models
from search_swe.wizard import select_setting


def fixture():
    return {"data": [
        {"id": "vendor/solver-v2", "name": "Vendor: Reasoning Solver",
         "context_length": 100000, "supported_parameters": ["tools", "reasoning"],
         "endpoints": ["/api/v1/responses"], "architecture": {"output_modalities": ["text"]}},
        {"id": "anthropic/claude-new", "name": "Claude New", "supported_parameters": ["tools", "reasoning_effort"],
         "endpoints": ["/api/v1/messages", "/api/v1/responses"]},
        {"id": "vendor/plain", "name": "Plain", "supported_parameters": ["tools"]},
        {"id": "vendor/no-tools", "supported_parameters": ["temperature"]},
        {"id": "vendor/image", "architecture": {"output_modalities": ["image"]}},
        {"id": "~vendor/solver-latest", "supported_parameters": ["tools"]},
    ]}


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "models.json"

    def test_live_catalog_then_cache_without_credentials(self):
        class Response(io.BytesIO):
            pass
        with patch("search_swe.model_catalog.urlopen", return_value=Response(json.dumps(fixture()).encode())) as request:
            models, source = load_models(cache=self.cache)
            self.assertEqual(source, "live")
            self.assertIn("vendor/solver-v2", models)
            self.assertNotIn("Authorization", request.call_args.args[0].headers)
        with patch("search_swe.model_catalog.urlopen") as request:
            self.assertEqual(load_models(cache=self.cache), (models, "cache"))
            request.assert_not_called()

    def test_refresh_failure_and_offline_use_stale_cache(self):
        self.cache.write_text(json.dumps({**fixture(), "fetched_at": 1}))
        with patch("search_swe.model_catalog.urlopen", side_effect=URLError("fixture offline")) as request:
            self.assertEqual(load_models(cache=self.cache, refresh=True)[1], "stale cache")
            request.assert_called_once()
        with patch("search_swe.model_catalog.urlopen") as request:
            self.assertEqual(load_models(cache=self.cache, offline=True, refresh=True)[1], "stale cache")
            request.assert_not_called()

    def test_corrupt_or_missing_catalog_keeps_manual_input_available(self):
        self.cache.write_text("not json")
        with patch("search_swe.model_catalog.urlopen", side_effect=TimeoutError):
            self.assertEqual(load_models(cache=self.cache), ({}, "unavailable"))
        self.assertEqual(load_models(cache=self.root / "missing", offline=True), ({}, "unavailable"))

    def test_capability_filters_and_terminal_text(self):
        data = fixture()
        data["data"][0]["name"] = "Solver\x1b\n"
        models = parse_models(data)
        self.assertEqual(models["vendor/solver-v2"]["name"], "Solver")
        self.assertTrue(eligible(models["vendor/solver-v2"], "codex"))
        self.assertFalse(eligible(models["vendor/solver-v2"], "claude-code"))
        self.assertTrue(eligible(models["anthropic/claude-new"], "claude-code"))
        self.assertFalse(eligible(models["vendor/no-tools"], "codex"))
        self.assertFalse(eligible(models["vendor/image"], "codex"))
        self.assertTrue(eligible({"id": "vendor/unlisted"}, "codex"))
        self.assertTrue(eligible(models["~vendor/solver-latest"], "codex"))

    def test_search_matches_name_and_id_and_returns_full_model_slug(self):
        completer = ModelCompleter(parse_models(fixture()))
        rows = list(completer.get_completions(Document("REASONING v2"), None))
        self.assertEqual([row.text for row in rows], ["vendor/solver-v2"])
        self.assertEqual(rows[0].start_position, -len("REASONING v2"))
        self.assertIn("100,000", rows[0].display_meta_text)
        self.assertEqual(list(completer.get_completions(Document("absent"), None)), [])

    def test_wizard_selects_harness_then_provider_then_search_then_effort(self):
        with patch("search_swe.wizard.load_models", return_value=(parse_models(fixture()), "live")), \
                patch("search_swe.wizard.ask", side_effect=["claude-code", "openrouter", "anthropic/claude-new", "default"]), \
                patch("search_swe.wizard.questionary.select") as select, \
                patch("search_swe.wizard.questionary.autocomplete") as autocomplete, redirect_stdout(io.StringIO()):
            setting = select_setting(Setting(), parser().parse_args(["configure"]))
        self.assertEqual(setting, Setting("claude-code", "openrouter", "anthropic/claude-new", "default"))
        self.assertEqual([call.args[0] for call in select.call_args_list], ["Harness", "Provider", "Reasoning / thinking level"])
        options = autocomplete.call_args.kwargs
        models = options["completer"].models
        self.assertEqual([model["id"] for model in models], ["anthropic/claude-new"])
        self.assertIsNot(options["validate"]("vendor/solver-v2"), True)
        self.assertIs(options["validate"]("anthropic/custom-model"), True)

    def test_model_without_reasoning_uses_default_and_pi_stays_direct(self):
        with patch("search_swe.wizard.load_models", return_value=(parse_models(fixture()), "cache")), \
                patch("search_swe.wizard.ask", side_effect=["codex", "openrouter", "vendor/plain"]), \
                patch("search_swe.wizard.questionary.select") as select, \
                patch("search_swe.wizard.questionary.autocomplete"), redirect_stdout(io.StringIO()):
            self.assertEqual(select_setting(Setting(), parser().parse_args(["configure"])).effort, "default")
        self.assertEqual(select.call_count, 2)
        with patch("search_swe.wizard.load_models") as load:
            with self.assertRaises(ValueError):
                select_setting(Setting(), parser().parse_args(["configure", "--agent", "pi", "--provider", "openrouter"]))
            load.assert_not_called()

    def test_model_default_reaches_harbor_as_null_and_omits_effort_flags(self):
        from harbor.cli.utils import parse_kwargs
        from scripts.harbor_agents import PreinstalledCodex, PreinstalledClaudeCode, PreinstalledPi
        for harness, model, cls, flag in (
            ("codex", "vendor/solver-v2", PreinstalledCodex, "reasoning_effort"),
            ("codex", "~vendor/solver-latest", PreinstalledCodex, "reasoning_effort"),
            ("claude-code", "anthropic/claude-new", PreinstalledClaudeCode, "reasoning_effort"),
            ("pi", "deepseek/deepseek-flash", PreinstalledPi, "thinking"),
        ):
            args = [sys.executable, str(ROOT / "scripts/run_task.py"), "--task", "reasoning-query-rewriting",
                    "--no-env-file", "--agent", harness, "--model", model, "--dry-run",
                    "--thinking" if harness == "pi" else "--reasoning-effort", "default"]
            if harness != "pi":
                args.append("--openrouter")
            env = {"PATH": os.environ["PATH"], "HOME": str(self.root)}
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"--ak {flag}=null", result.stdout)
            with patch.dict(os.environ, env, clear=True):
                agent = cls(logs_dir=self.root / harness, model_name=model, **parse_kwargs([f"{flag}=null"]))
            self.assertNotIn(flag, agent._resolved_flags)
            self.assertNotIn("--effort", agent.build_cli_flags())
            self.assertNotIn("model_reasoning_effort", agent.build_cli_flags())
            self.assertNotIn("--thinking", agent.build_cli_flags())


if __name__ == "__main__":
    unittest.main()
