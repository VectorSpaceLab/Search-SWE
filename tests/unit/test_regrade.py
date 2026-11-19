from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from harbor.models.trial.config import TrialConfig

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from search_swe.cli import main
from search_swe.regrade import result_summary


def fixture(work):
    checkout = work / "checkout"
    checkout.mkdir()
    for name in ("scripts", "environments", "src"):
        (checkout / name).symlink_to(ROOT / name, target_is_directory=True)
    (checkout / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
    task = checkout / "tasks/fixture-regrade"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Fixture.")
    (task / "assets.json").write_text('{"schema_version": 1, "files": []}')
    (task / "task.toml").write_text("""
artifacts = ["/app/submission", "/logs/agent/trajectory.json"]
[task]
name = "search-swe/fixture-regrade"
[environment]
cpus = 1
memory_mb = 512
network_mode = "no-network"
[verifier]
environment_mode = "separate"
""")
    source = work / "original"
    (source / "agent").mkdir(parents=True)
    (source / "artifacts/app/submission").mkdir(parents=True)
    (source / "artifacts/logs/agent").mkdir(parents=True)
    (source / "artifacts/app/submission/answer.txt").write_text("recorded!")
    (source / "artifacts/logs/agent/trajectory.json").write_text('{"recorded": true}')
    (source / "artifacts/manifest.json").write_text(json.dumps([
        {"source": "/logs/artifacts", "destination": "artifacts/logs/artifacts", "type": "directory", "status": "empty"},
        {"source": "/app/submission", "destination": "artifacts/app/submission", "type": "directory", "status": "ok"},
        {"source": "/logs/agent/trajectory.json", "destination": "artifacts/logs/agent/trajectory.json",
         "type": "file", "status": "ok"},
    ]))
    config = {"task": {"path": str(task)}, "agent": {"name": "codex", "model_name": "provider/original"}}
    result = {"id": str(uuid4()), "task_name": "search-swe/fixture-regrade", "trial_name": "original",
              "trial_uri": source.as_uri(), "task_id": {"path": str(task)}, "task_checksum": "original-hash",
              "config": config, "agent_info": {"name": "codex", "version": "test",
                                               "model_info": {"name": "original", "provider": "provider"}}}
    (source / "config.json").write_text(json.dumps(config))
    (source / "result.json").write_text(json.dumps(result))
    return checkout, task, source, result


class RegradeTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.checkout, self.task, self.source, self.original = fixture(Path(directory.name))
        self.output = Path(directory.name) / "new-output"
        self.args = ["regrade", str(self.source), "--repo", str(self.checkout), "--output", str(self.output)]
        environment = patch.dict(os.environ, {"PATH": os.environ["PATH"]}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def invoke(self, *args):
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
            code = main([*self.args, *args])
        return code, output.getvalue() + error.getvalue()

    def test_preview_checks_inputs_without_side_effects(self):
        with patch("search_swe.runner.doctor", side_effect=AssertionError("started preflight")):
            code, output = self.invoke("--dry-run")
            self.assertEqual(code, 0, output)
            self.assertIn(self.original["id"], output)
            self.assertFalse(self.output.exists())
            (self.source / "artifacts/logs/agent/trajectory.json").unlink()
            code, output = self.invoke("--dry-run")
            self.assertEqual(code, 1, output)
            self.assertIn("/logs/agent/trajectory.json", output)

    def test_source_symlinks_are_rejected_before_replay(self):
        (self.source / "agent/other").symlink_to(self.source / "result.json")
        code, output = self.invoke("--dry-run")
        self.assertEqual(code, 1, output)
        self.assertIn("Only regular files and directories", output)

    def test_only_verifier_is_configured_and_zero_reward_is_preserved(self):
        from search_swe import runner
        launcher = runner.backend(self.checkout, "evaluation/run_task")
        space = runner.backend(self.checkout, "assets/asset_space")
        (self.task / "task.toml").write_text((self.task / "task.toml").read_text().replace(
            'network_mode = "no-network"', 'network_mode = "allowlist"\nallowed_hosts = ["openrouter.ai"]'
        ) + '\n[verifier.env]\nOPENAI_API_KEY = "${VERIFIER_OPENAI_API_KEY:-}"\n')
        task = self.task / "environment/docker-compose.yaml"
        task.write_text("services: {}\n")
        new_id = str(uuid4())
        original_source = (self.source / "result.json").read_bytes()

        def execute(command, env, cwd):
            if command[0] == sys.executable:
                self.assertIn("--local-files-only", command)
                return 0
            self.assertEqual(command[:4], ["harbor", "trial", "start", "--config"])
            config_path = Path(command[4])
            raw_config = config_path.read_text()
            self.assertNotIn("verifier-token", raw_config)
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
            config = TrialConfig.model_validate_json(raw_config)
            self.assertEqual(config.agent.name, "nop")
            self.assertEqual(config.source_trial.action, "regrade")
            self.assertEqual(config.source_trial.path, self.source)
            self.assertEqual(str(config.source_trial.trial_id), self.original["id"])
            self.assertEqual(config.verifier.env["OPENAI_API_KEY"], "${VERIFIER_OPENAI_API_KEY}")
            self.assertTrue(config.environment.import_path.endswith(":PhaseScopedDocker"))
            trial = config.trials_dir / config.trial_name
            (trial / "verifier").mkdir(parents=True)
            (trial / "verifier/judge-status.json").write_text('{"measurement_valid": true}')
            (trial / "result.json").write_text(json.dumps({
                **self.original, "id": new_id, "trial_name": config.trial_name, "task_checksum": "current-hash",
                "verifier_result": {"rewards": {"reward": 0}},
            }))
            return 0

        with patch.dict(os.environ, {"VERIFIER_OPENAI_API_KEY": "verifier-token"}), \
                patch.object(launcher, "run_command", side_effect=execute), \
                patch.object(runner, "backend", side_effect=[launcher, space]), \
                patch.object(runner, "doctor"), patch.object(runner, "asset_plan", return_value={}), \
                patch.object(space, "describe"), patch.object(space, "validate"):
            code, output = self.invoke("--offline")
        self.assertEqual(code, 0, output)
        report = json.loads((self.output / "regrade.json").read_text())
        self.assertEqual(report["source_trial_id"], self.original["id"])
        self.assertEqual(report["trial_id"], new_id)
        self.assertEqual(report["task_checksum"], "current-hash")
        self.assertEqual(report["rewards"], {"reward": 0.0})
        self.assertTrue(report["measurement_valid"])
        self.assertEqual(original_source, (self.source / "result.json").read_bytes())

        trial = Path(report["trial"])
        (trial / "verifier/judge-status.json").unlink()
        result_summary(trial, report)
        self.assertIsNone(report["measurement_valid"])
        for health in ({"measurement_valid": False},
                       {"final_gate": {"evaluation_valid": True, "judge_succeeded": False}}):
            (trial / "verifier/reward-details.json").write_text(json.dumps(health))
            result_summary(trial, report)
            self.assertEqual(report["status"], "invalid-measurement")
            self.assertFalse(report["measurement_valid"])
