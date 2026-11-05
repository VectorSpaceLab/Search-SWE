"""Incremental task-specific setup, without provider requests or real credentials."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from search_swe import wizard
from search_swe.cli import main
from search_swe.configuration import Setting, read_env, save_env
from search_swe.repository import discover
from search_swe.submission_models import EXCLUDED_MODEL, PROFILES


class CredentialSetupTests(unittest.TestCase):
    def test_optional_key_can_be_disabled_saved_and_skipped_by_probes(self):
        from search_swe.submission_checks import verify_submission_keys
        env = {"OPENROUTER_API_KEY": "fixture-old-key"}
        updates = {}
        with patch.object(wizard, "ask", return_value="Disable / clear"), redirect_stdout(io.StringIO()):
            wizard.credential("OPENROUTER_API_KEY", env, updates, optional=True, edit=True)
        self.assertEqual(updates, {"OPENROUTER_API_KEY": ""})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            save_env(path, {"OPENROUTER_API_KEY": "fixture-old-key", "UNRELATED": "keep"})
            save_env(path, updates)
            self.assertEqual(read_env(path), {"OPENROUTER_API_KEY": "", "UNRELATED": "keep"})
        with patch("search_swe.submission_checks.load_models", side_effect=AssertionError("disabled key probed")):
            verify_submission_keys([self.catalog["code-context-retrieval"]], env)

    def test_required_keys_have_no_disable_action(self):
        with patch.object(wizard, "ask", return_value="Keep existing"), patch.object(wizard.questionary, "select") as select:
            wizard.credential("OPENROUTER_API_KEY", {"OPENROUTER_API_KEY": "fixture"}, {}, edit=True)
        self.assertNotIn("Disable / clear", select.call_args.kwargs["choices"])

    @classmethod
    def setUpClass(cls):
        cls.catalog = discover(ROOT)

    def setUp(self):
        self.env = {"AGENT_OPENROUTER_API_KEY": "fixture-agent-private",
                    "VERIFIER_OPENAI_API_KEY": "fixture-judge-private",
                    "VERIFIER_OPENAI_BASE_URL": "https://openrouter.ai/api/v1"}

    def test_all_tasks_classify_only_their_referenced_variables(self):
        for task in self.catalog.values():
            with self.subTest(task=task.name):
                required, optional = task.required_variables(), task.optional_variables()
                self.assertFalse(required & optional)
                self.assertEqual(required | optional, task.variables())
                self.assertLessEqual(task.configuration().keys(), task.variables())
        plain = self.catalog["code-context-retrieval"]
        self.assertEqual(plain.required_variables(), set())
        self.assertEqual(plain.optional_variables(), {"OPENROUTER_API_KEY", "JINA_API_KEY"})
        gpu = self.catalog["code-embedding-finetuning"]
        self.assertEqual(gpu.required_variables(), {"VERIFIER_OPENAI_API_KEY", "VERIFIER_OPENAI_BASE_URL"})
        self.assertEqual(gpu.optional_variables(), set())

    def test_required_answerer_key_and_configurable_judge_mappings(self):
        task = self.catalog["icsi-meeting-memory"]
        self.assertEqual(task.required_variables(), {"OPENROUTER_API_KEY", "ANSWER_JUDGE_MODEL_NAME",
                                                    "ANSWER_JUDGE_API_KEY", "ANSWER_JUDGE_BASE_URL",
                                                    "VERIFIER_OPENAI_API_KEY", "VERIFIER_OPENAI_BASE_URL"})
        self.assertEqual(task.optional_variables(), {"JINA_API_KEY"})
        task = self.catalog["long-pdf-evidence"]
        self.assertIn("ANSWER_JUDGE_API_KEY", task.required_variables())
        self.assertIn("ANSWER_JUDGE_MODEL_NAME", task.required_variables())
        self.assertIn("ANSWER_JUDGE_BASE_URL", task.required_variables())

    def test_existing_agent_and_task_credentials_need_no_questions(self):
        self.env.update(OPENROUTER_API_KEY="fixture-submission-private", JINA_API_KEY="fixture-jina-private")
        updates = {}
        with patch.object(wizard, "ask") as ask, redirect_stdout(io.StringIO()) as output:
            wizard.configure_agent(Setting(), self.env, updates)
            wizard.configure_task_services([self.catalog["agentic-search"], self.catalog["code-context-retrieval"]], self.env, updates)
        ask.assert_not_called()
        self.assertEqual(updates, {})
        for value in ("fixture-agent-private", "fixture-judge-private", "fixture-submission-private"):
            self.assertNotIn(value, output.getvalue())

    def test_new_task_only_requests_its_missing_namespaced_service(self):
        self.env.update(OPENROUTER_API_KEY="fixture-shared-private", JINA_API_KEY="fixture-jina-private")
        name = "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY"
        updates = {}
        with patch.object(wizard, "ask", side_effect=[[name], "fixture-restricted-private"]) as ask, \
                patch.object(wizard.questionary, "checkbox") as checkbox, \
                patch.object(wizard.questionary, "password") as password, redirect_stdout(io.StringIO()) as output:
            wizard.configure_task_services([self.catalog["agentic-search"], self.catalog["reasoning-query-rewriting"]], self.env, updates)
        self.assertEqual(ask.call_count, 2)
        self.assertEqual([choice.value for choice in checkbox.call_args.kwargs["choices"]], [name])
        self.assertEqual(updates, {name: "fixture-restricted-private"})
        self.assertIn(name, password.call_args.args[0])
        self.assertIn("assign", output.getvalue())
        self.assertIn("qwen/qwen3.5-9b", output.getvalue())
        self.assertNotIn("fixture-restricted-private", output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            save_env(path, {"OPENROUTER_API_KEY": "fixture-shared-private", "UNRELATED": "keep"})
            save_env(path, updates)
            self.assertEqual(read_env(path), {"OPENROUTER_API_KEY": "fixture-shared-private", "UNRELATED": "keep", **updates})

    def test_optional_services_can_be_skipped_and_shared_fields_are_asked_once(self):
        tasks = [self.catalog["agentic-search"], self.catalog["code-context-retrieval"]]
        with patch.object(wizard, "ask", return_value=[]), patch.object(wizard.questionary, "checkbox") as checkbox, \
                patch.object(wizard.questionary, "password") as password, redirect_stdout(io.StringIO()):
            wizard.configure_task_services(tasks, self.env, {})
        self.assertEqual({choice.value for choice in checkbox.call_args.kwargs["choices"]}, {"OPENROUTER_API_KEY", "JINA_API_KEY"})
        password.assert_not_called()
        self.assertNotIn("OPENROUTER_API_KEY", self.env)

    def test_existing_restricted_key_gets_guidance_without_reentry(self):
        self.env.update(REASONING_QUERY_REWRITING_OPENROUTER_API_KEY="fixture-restricted-private", JINA_API_KEY="fixture-jina-private")
        with patch.object(wizard, "ask") as ask, redirect_stdout(io.StringIO()) as output:
            wizard.configure_task_services([self.catalog["reasoning-query-rewriting"]], self.env, {})
        ask.assert_not_called()
        self.assertIn("qwen/qwen3.6-35b-a3b", output.getvalue())
        self.assertIn("guardrail", output.getvalue())
        self.assertNotIn("fixture-restricted-private", output.getvalue())

    def test_explicit_edit_replaces_only_the_selected_credential(self):
        updates = {}
        with patch.object(wizard, "ask", side_effect=["Replace", "fixture-new-private"]) as ask, redirect_stdout(io.StringIO()):
            wizard.configure_agent(Setting(), self.env, updates, edit=True)
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(updates, {"AGENT_OPENROUTER_API_KEY": "fixture-new-private"})
        self.assertEqual(self.env["VERIFIER_OPENAI_API_KEY"], "fixture-judge-private")

    def test_new_required_task_service_is_not_in_the_optional_menu(self):
        self.env.update(ANSWER_JUDGE_MODEL_NAME="vendor/judge", ANSWER_JUDGE_API_KEY="fixture-answer-judge-private",
                        ANSWER_JUDGE_BASE_URL="https://openrouter.ai/api/v1", JINA_API_KEY="fixture-jina-private")
        with patch.object(wizard, "ask", return_value="fixture-answerer-private") as ask, \
                patch.object(wizard.questionary, "password") as password, \
                patch.object(wizard.questionary, "checkbox") as checkbox, redirect_stdout(io.StringIO()):
            wizard.configure_task_services([self.catalog["icsi-meeting-memory"]], self.env, {})
        ask.assert_called_once()
        self.assertEqual(password.call_args.args[0], "OPENROUTER_API_KEY (required)")
        checkbox.assert_not_called()

    def test_preview_is_secret_free_and_lists_only_selection_needs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.env"
            save_env(path, {**self.env, "UNRELATED_API_KEY": "fixture-unrelated-private"})
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
                code = main(["configure", "reasoning-query-rewriting", "--repo", str(ROOT), "--env-file", str(path), "--dry-run"])
            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(set(report["credentials"]["required"]), set(self.env))
            self.assertEqual(set(report["credentials"]["optional"]), {"REASONING_QUERY_REWRITING_OPENROUTER_API_KEY", "JINA_API_KEY"})
            self.assertNotIn("fixture-", output.getvalue())
            self.assertNotIn("UNRELATED_API_KEY", output.getvalue())
            self.assertIn("guardrail", output.getvalue())

    def test_scripted_missing_credentials_report_exact_task_and_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new file.env"
            with patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
                code = main(["run", "icsi-meeting-memory", "--repo", str(ROOT), "--env-file", str(path), "--yes"])
            self.assertEqual(code, 1)
            message = error.getvalue()
            self.assertIn("ANSWER_JUDGE_MODEL_NAME, OPENROUTER_API_KEY", message)
            self.assertIn("search-swe configure", message)
            self.assertIn(str(path), message)
            self.assertIn("icsi-meeting-memory", message)
            self.assertNotIn("JINA_API_KEY", message)
            self.assertFalse(path.exists())

    def test_native_preflight_requires_answerer_but_not_optional_rewriting_key(self):
        env = {**self.env, "PATH": os.environ["PATH"], "ANSWER_JUDGE_MODEL_NAME": "vendor/judge",
               "ANSWER_JUDGE_API_KEY": "fixture-answer-judge-private", "ANSWER_JUDGE_BASE_URL": "https://openrouter.ai/api/v1"}
        command = [sys.executable, str(ROOT / "scripts/evaluation/run_task.py"), "--no-env-file", "--agent", "codex",
                   "--openrouter", "--model", "openai/gpt-6-luna", "--check"]
        missing = subprocess.run([*command, "--task", "icsi-meeting-memory"], env=env, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("OPENROUTER_API_KEY", missing.stderr)
        for task in ("icsi-meeting-memory", "reasoning-query-rewriting", "code-embedding-finetuning"):
            with self.subTest(task=task):
                configured = dict(env, OPENROUTER_API_KEY="fixture-answerer-private")
                result = subprocess.run([*command, "--task", task], env=configured, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rewriting_guidance_tracks_the_public_model_allowlist(self):
        task = self.catalog["reasoning-query-rewriting"]
        public = (task.path / "environment/docs/available_resources.md").read_text()
        guidance = task.configuration()["REASONING_QUERY_REWRITING_OPENROUTER_API_KEY"]["guidance"]
        model = r"qwen/[a-z0-9]+(?:[.-][a-z0-9]+)*"
        expected = set(PROFILES["reasoning-query-rewriting"]["generation"])
        self.assertEqual(set(re.findall(model, guidance)) - {EXCLUDED_MODEL}, expected)
        self.assertEqual(set(re.findall(model, public)), expected)
        self.assertNotIn("OPENROUTER_API_KEY", task.optional_variables())


if __name__ == "__main__":
    unittest.main()
