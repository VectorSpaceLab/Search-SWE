"""Submission model profiles and mandatory probes; all provider I/O is mocked."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from search_swe import cli, submission_checks as checks, wizard
from search_swe.configuration import Setting
from search_swe.repository import discover
from search_swe.submission_models import EXCLUDED_MODEL, PROFILES, model_ids


def catalog():
    names = [f"vendor{vendor}/model{index}" for vendor in range(8) for index in range(10)]
    names.extend(PROFILES["shared"]["generation"])
    return {name: {"id": name, "output_modalities": ["text"], "supported_parameters": ["max_tokens"]} for name in names}


def denial(status=403, message="Model is not allowed by your guardrail", metadata=None):
    body = {"error": {"code": status, "message": message}}
    if metadata is not None:
        body["error"]["metadata"] = metadata
    return HTTPError(checks.CHAT_URL, status, "fixture", {}, io.BytesIO(json.dumps(body).encode()))


def guardrail_metadata():
    return {"failed_routing_step": "Filter by Guardrails", "input_endpoint_count": 2,
            "ineligibility_reasons": [{"reason": "model-ignored-by-guardrail", "endpoint_count": 2}]}


class SubmissionModelTests(unittest.TestCase):
    def test_exact_profile_counts_and_documented_ids(self):
        shared, rewriting = model_ids("shared"), model_ids("reasoning-query-rewriting")
        self.assertEqual(len(shared), 47)
        self.assertEqual(len(rewriting), 17)
        self.assertEqual(len(set(shared)), 47)
        self.assertEqual(len(set(rewriting)), 17)
        self.assertLess(set(rewriting), set(shared))
        self.assertNotIn(EXCLUDED_MODEL, shared)
        self.assertIn("openai/text-embedding-3-large:batch", shared)
        self.assertIn("nvidia/nemotron-3-embed-1b:free", shared)
        document = (ROOT / "docs/evaluation/submission-models.md").read_text()
        shared_text = document.split("## Shared: 47 models")[1].split("## Reasoning query rewriting: 17 models")[0]
        listed = re.findall(r"\| `([^`]+)` \|", shared_text)
        self.assertEqual(set(listed), set(shared))
        rewriting_text = document.split("## Reasoning query rewriting: 17 models")[1].split("## Sources")[0]
        self.assertEqual(set(re.findall(r"- `([^`]+)`", rewriting_text)), set(rewriting))

    def test_model_export_needs_no_repo_credentials_or_network(self):
        with patch.object(cli, "find_repo", side_effect=AssertionError("repo accessed")), \
                patch.object(checks, "load_models", side_effect=AssertionError("network accessed")), \
                patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
            code = cli.main(["submission-models", "--profile", "reasoning-query-rewriting", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), {"allowed_models": model_ids("reasoning-query-rewriting")})

    def test_sampling_is_diverse_outside_allowlist_and_checks_stricter_boundary(self):
        for profile in PROFILES:
            selected = set()
            for _ in range(20):
                models = checks.probe_models(profile, catalog())
                self.assertEqual(len(models), 3)
                self.assertEqual(len({name.split("/")[0] for name in models}), 3)
                self.assertFalse(set(models) & set(model_ids(profile)))
                if profile == "reasoning-query-rewriting":
                    self.assertEqual(models[0], "qwen/qwen3-30b-a3b-instruct-2507")
                selected.update(models)
            self.assertGreater(len(selected), 3)
        with self.assertRaisesRegex(ValueError, "too few"):
            checks.probe_models("shared", dict(list(catalog().items())[:3]))

    def test_ambiguous_failures_are_not_model_denials(self):
        for status, message, metadata in [
            (401, "Model is not allowed", None), (404, "No endpoints found", None),
            (403, "Forbidden", None), (403, "Model budget limit exceeded", {"limit_source": "openrouter_guardrail_budget"}),
            (403, "Model not allowed in your region", None), (403, "Model provider is not allowed", None),
            (403, "Model is not allowed", {"provider_name": "Vendor"}),
            (403, "Model not allowed", {"reasons": ["moderation"]}),
            (403, "Prompt injection patterns detected", None),
        ]:
            with self.subTest(status=status, message=message):
                self.assertFalse(checks.model_access_denied(status, {"error": {"code": status, "message": message, "metadata": metadata}}))
        for message in ("Model is not allowed by your guardrail", "Model foo/bar is not permitted",
                        "The requested model is not in your allowlist", "Model access denied"):
            self.assertTrue(checks.model_access_denied(403, {"error": {"code": 403, "message": message}}))
        for malformed in ([], None, {"error": "Model not allowed"}, {"error": {"code": 403, "message": []}}):
            self.assertFalse(checks.model_access_denied(403, malformed))

    def test_explicit_model_guardrail_404_is_recognized(self):
        for count in (1, 2, 12):
            metadata = guardrail_metadata()
            metadata["input_endpoint_count"] = count
            metadata["ineligibility_reasons"][0]["endpoint_count"] = count
            for message in ("Model blocked by guardrail", "MODEL BLOCKED BY GUARDRAIL."):
                with self.subTest(count=count, message=message):
                    self.assertTrue(checks.model_access_denied(
                        404, {"error": {"code": 404, "message": message, "metadata": metadata}}))

    def test_guardrail_404_requires_complete_model_only_endpoint_exclusion(self):
        valid = guardrail_metadata()
        invalid = [None, {}, [], "guardrail",
                   {**valid, "failed_routing_step": "Filter by Provider"},
                   {**valid, "ineligibility_reasons": []},
                   {**valid, "ineligibility_reasons": [None]},
                   {**valid, "ineligibility_reasons": valid["ineligibility_reasons"] * 2}]
        for count in (None, 0, -1, True, "2", 2.0):
            invalid.append({**valid, "input_endpoint_count": count})
        for count in (None, 0, 1, True, "2", 2.0):
            invalid.append({**valid, "ineligibility_reasons": [
                {"reason": "model-ignored-by-guardrail", "endpoint_count": count}]})
        for reason in ("provider-ignored-by-guardrail", "zdr-required", "budget-exceeded"):
            invalid.append({**valid, "ineligibility_reasons": [{"reason": reason, "endpoint_count": 2}]})
        for key in ("raw", "provider_name", "limit_source", "reasons", "flagged_input", "patterns"):
            invalid.append({**valid, key: "fixture"})
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                self.assertFalse(checks.model_access_denied(404, {"error": {
                    "code": 404, "message": "Model blocked by guardrail", "metadata": metadata}}))

    def test_guardrail_404_requires_consistent_status_and_explicit_message(self):
        for status, code, message in (
            (403, 404, "Model blocked by guardrail"), (404, 403, "Model blocked by guardrail"),
            (404, "404", "Model blocked by guardrail"), (404, None, "Model blocked by guardrail"),
            (401, 401, "Model blocked by guardrail"), (500, 500, "Model blocked by guardrail"),
            (404, 404, "No endpoints found"), (404, 404, "Guardrail blocked request"),
            (404, 404, "Model blocked by guardrail: provider restriction"),
            (404, 404, "Model blocked by guardrail: insufficient credits"), (404, 404, []),
        ):
            with self.subTest(status=status, code=code, message=message):
                self.assertFalse(checks.model_access_denied(status, {"error": {
                    "code": code, "message": message, "metadata": guardrail_metadata()}}))

    def test_guardrail_404_completes_three_probes_for_each_selected_profile(self):
        task = Mock()
        task.variables.return_value = {"OPENROUTER_API_KEY", "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY"}
        env = {"OPENROUTER_API_KEY": "shared-private", "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY": "rqr-private"}
        opener = Mock()
        opener.open.side_effect = lambda *a, **kw: denial(404, "Model blocked by guardrail", guardrail_metadata())
        with patch.object(checks, "load_models", return_value=(catalog(), "live")), \
                patch.object(checks, "build_opener", return_value=opener), redirect_stdout(io.StringIO()) as output:
            checks.verify_submission_keys([task], env)
        self.assertEqual(opener.open.call_count, 6)
        self.assertEqual(output.getvalue().count("all 3 sampled models were denied"), 2)
        self.assertNotIn("-private", output.getvalue())
        for key in env.values():
            requests = [call.args[0] for call in opener.open.call_args_list
                        if call.args[0].get_header("Authorization") == f"Bearer {key}"]
            self.assertEqual(len(requests), 3)
            payloads = [json.loads(request.data) for request in requests]
            self.assertEqual(len({payload["model"] for payload in payloads}), 3)
            self.assertTrue(all(payload["max_tokens"] == 1 for payload in payloads))

    def test_probe_is_one_token_fixed_endpoint_and_hides_secret(self):
        opener = Mock()
        opener.open.side_effect = denial()
        checks.check_probe(opener, "fixture-secret", "shared", "vendor/model")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, checks.CHAT_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret")
        payload = json.loads(request.data)
        self.assertEqual(payload["max_tokens"], 1)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "vendor/model")
        self.assertNotIn("tools", payload)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)
        for status in (401, 402, 403, 404, 429, 500):
            opener.open.side_effect = denial(status, "fixture-secret")
            with self.assertRaises(ValueError) as caught:
                checks.check_probe(opener, "fixture-secret", "shared", "vendor/model")
            self.assertNotIn("fixture-secret", str(caught.exception))
            self.assertIn(f"HTTP {status}", str(caught.exception))
        opener.open.side_effect = URLError("fixture-secret")
        with self.assertRaisesRegex(ValueError, "network/request failure") as caught:
            checks.check_probe(opener, "fixture-secret", "shared", "vendor/model")
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertIsNone(checks.NoRedirect().redirect_request(None, None, 307, "", {}, "https://elsewhere.test"))

    def test_any_accepted_request_blocks_including_error_in_200_body(self):
        for payload in ({"choices": [{"message": {"content": "OK"}}]}, {"error": {"code": 500}}):
            opener = Mock()
            response = Mock(status=200)
            response.read.return_value = json.dumps(payload).encode()
            opener.open.return_value.__enter__ = Mock(return_value=response)
            opener.open.return_value.__exit__ = Mock(return_value=False)
            with self.assertRaisesRegex(ValueError, "accepted out-of-list model vendor/model"):
                checks.check_probe(opener, "fixture-secret", "shared", "vendor/model")

    def test_checks_only_enabled_selected_submission_keys_and_never_cache_results(self):
        task = Mock()
        task.variables.return_value = {"OPENROUTER_API_KEY", "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY"}
        env = {"OPENROUTER_API_KEY": "shared-private", "REASONING_QUERY_REWRITING_OPENROUTER_API_KEY": "rqr-private",
               "AGENT_OPENROUTER_API_KEY": "agent-private", "VERIFIER_OPENAI_API_KEY": "judge-private"}
        opener = Mock()
        opener.open.side_effect = lambda *a, **kw: denial()
        with patch.object(checks, "load_models", return_value=(catalog(), "live")) as load, \
                patch.object(checks, "build_opener", return_value=opener), redirect_stdout(io.StringIO()) as output:
            checks.verify_submission_keys([task], env)
            self.assertEqual(opener.open.call_count, 6)
            self.assertEqual({call.args[0].get_header("Authorization") for call in opener.open.call_args_list},
                             {"Bearer shared-private", "Bearer rqr-private"})
            checks.verify_submission_keys([task], env)
            self.assertEqual(opener.open.call_count, 12)
            self.assertEqual(load.call_count, 2)
            self.assertNotIn("-private", output.getvalue())
            load.reset_mock()
            checks.verify_submission_keys([], env)
            checks.verify_submission_keys([task], {"OPENROUTER_API_KEY": " "})
            load.assert_not_called()

    def test_no_stale_catalog_or_successful_probe_can_pass(self):
        task = Mock()
        task.variables.return_value = {"OPENROUTER_API_KEY"}
        with patch.object(checks, "load_models", return_value=(catalog(), "stale cache")), \
                patch.object(checks, "check_probe") as probe, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "fresh OpenRouter"):
                checks.verify_submission_keys([task], {"OPENROUTER_API_KEY": "private"})
            probe.assert_not_called()
        with patch.object(checks, "load_models", return_value=(catalog(), "live")), \
                patch.object(checks, "check_probe", side_effect=ValueError("Invalid submission allowlist")) as probe, \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Invalid submission"):
                checks.verify_submission_keys([task], {"OPENROUTER_API_KEY": "private"})
            probe.assert_called_once()

    def test_cli_gate_precedes_save_and_launch_and_applies_to_yes_offline(self):
        env = {"AGENT_OPENROUTER_API_KEY": "fixture-agent", "VERIFIER_OPENAI_API_KEY": "fixture-judge",
               "OPENROUTER_API_KEY": "fixture-submission"}
        for command in ("configure", "run"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "local.env"
                with patch.dict(os.environ, env, clear=True), patch.object(cli.runner, "preflight"), \
                        patch.object(cli.runner, "doctor"), patch.object(cli.Pool, "host", return_value=Mock(cpus=[0], memory_mb=65536, gpus=[])), \
                        patch.object(cli, "check_config_destination"), patch.object(cli, "save_env") as save, \
                        patch.object(cli.runner, "run_batch") as run, \
                        patch.object(cli, "verify_submission_keys", side_effect=ValueError("Invalid submission allowlist")) as gate, \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
                    code = cli.main([command, "agentic-search", "--repo", str(ROOT), "--env-file", str(path), "--yes", "--offline"])
                self.assertEqual(code, 1, error.getvalue())
                self.assertIn("Invalid submission allowlist", error.getvalue())
                gate.assert_called_once()
                self.assertEqual(gate.call_args.args[0][0].name, "agentic-search")
                save.assert_not_called()
                run.assert_not_called()
                self.assertFalse(path.exists())

    def test_successful_cli_configuration_validates_before_saving(self):
        env = {"AGENT_OPENROUTER_API_KEY": "fixture-agent", "OPENROUTER_API_KEY": "fixture-submission"}
        events = []
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env, clear=True), \
                patch.object(cli.runner, "preflight"), patch.object(cli, "check_config_destination"), \
                patch.object(cli, "verify_submission_keys", side_effect=lambda *args: events.append("check")), \
                patch.object(cli, "save_env", side_effect=lambda *args: events.append("save")), \
                redirect_stdout(io.StringIO()):
            code = cli.main(["configure", "code-context-retrieval", "--repo", str(ROOT),
                             "--env-file", str(Path(directory) / "local.env"), "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(events, ["check", "save"])

    def test_existing_profile_hint_is_shown_once_when_editing(self):
        tasks = [discover(ROOT)["code-context-retrieval"]]
        env = {"OPENROUTER_API_KEY": "fixture-shared", "JINA_API_KEY": "fixture-jina"}
        with patch.object(wizard, "ask", side_effect=[["OPENROUTER_API_KEY"], "Keep existing"]), redirect_stdout(io.StringIO()) as output:
            wizard.configure_task_services(tasks, env, {}, edit=True)
        self.assertEqual(output.getvalue().count("REQUIRED fixed 47-model"), 1)

    def test_dry_run_and_cancel_do_not_probe(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENT_OPENROUTER_API_KEY": "fixture"}, clear=True), \
                patch.object(cli, "verify_submission_keys") as gate, patch.object(cli.runner, "preflight"), \
                patch.object(cli.sys.stdin, "isatty", return_value=True), patch.object(cli.sys.stdout, "isatty", return_value=True), \
                patch.object(wizard, "select_setting", return_value=Setting()), patch.object(wizard, "configure_agent"), \
                patch.object(wizard, "configure_task_services"), patch.object(wizard, "concurrency", return_value=1), \
                patch.object(wizard, "ask", return_value=False), redirect_stdout(io.StringIO()):
            base = ["configure", "code-context-retrieval", "--repo", str(ROOT), "--env-file", str(Path(directory) / "local.env")]
            self.assertEqual(cli.main([*base, "--dry-run"]), 0)
            # Use configure_run directly because redirected stdout is not a terminal.
            with patch.object(cli.sys.stdout, "isatty", return_value=True):
                self.assertEqual(cli.configure_run(cli.parser().parse_args(base), ROOT), 0)
            gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
