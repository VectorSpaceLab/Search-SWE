import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("agentic_search_vectorless_trajectory_gate", Path(__file__).with_name("trajectory_gate.py"))
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class RewardTests(unittest.TestCase):
    def test_valid_audit_gates_gold_recall(self):
        cases = [
            ({"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": 0.7}}, 0.7),
            ({"valid": False, "primary_metric": {"name": "GoldRecall@5", "value": 1}}, 0.0),
            ({"valid": True, "primary_metric": {"name": "other_metric", "value": 1}}, 0.0),
            ({"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": float("nan")}}, 0.0),
            ({}, 0.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(VERIFY, "REWARD_DIR", root):
                for report, expected in cases:
                    with self.subTest(report=report):
                        self.assertEqual(VERIFY.write_reward(report, {"jailbreak_judge": 1}, execution_ok=True,
                                                            audit_status=0, trajectory_present=True), expected)
                        self.assertEqual(float((root / "reward.txt").read_text()), expected)
                        self.assertEqual(json.loads((root / "reward.json").read_text()),
                                         {"gold_recall_at_5": expected, "jailbreak_judge": 1.0, "reward": expected})

    def test_audit_failures_cannot_produce_positive_reward(self):
        report = {"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": 0.7}}
        cases = [({}, True, 0, True), ({"jailbreak_judge": 0}, True, 0, True),
                 ({"jailbreak_judge": 1}, False, 0, True),
                 ({"jailbreak_judge": 1}, True, 124, True),
                 ({"jailbreak_judge": 1}, True, 0, False),
                 ({"jailbreak_judge": "1"}, True, 0, True),
                 ({"jailbreak_judge": float("nan")}, True, 0, True)]
        with tempfile.TemporaryDirectory() as directory, patch.object(VERIFY, "REWARD_DIR", Path(directory)):
            for audit, execution_ok, status, present in cases:
                with self.subTest(audit=audit, status=status, present=present):
                    self.assertEqual(VERIFY.write_reward(report, audit, execution_ok=execution_ok,
                                                        audit_status=status, trajectory_present=present), 0)
            self.assertEqual(VERIFY.write_reward(report), 0)

    def test_orchestrator_stops_workers_before_audit_and_fails_closed(self):
        for mode in ("pass", "reject", "timeout", "malformed", "missing-trajectory", "execution-failed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                results = root / "results"
                report = results / "evaluation.json"
                trajectory = root / "trajectory.json"
                audit_path = root / "audit.json"
                if mode != "missing-trajectory":
                    trajectory.write_text('{"steps": [{"role": "agent"}]}')
                events = []

                def retrieval(*args, **kwargs):
                    events.append("retrieval")
                    report.write_text(json.dumps({"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": 0.7}}))
                    return subprocess.CompletedProcess(args[0], 1 if mode == "execution-failed" else 0)

                def audit():
                    self.assertEqual(events, ["retrieval", "stopped"])
                    self.assertEqual(float((root / "reward.txt").read_text()), 0)
                    events.append("audit")
                    if mode == "timeout":
                        raise subprocess.TimeoutExpired("judge", 3600)
                    audit_path.write_text("invalid" if mode == "malformed" else json.dumps({"jailbreak_judge": 0 if mode == "reject" else 1}))
                    return 0

                with patch.multiple(VERIFY, REWARD_DIR=root, RESULTS_DIR=results,
                                    REPORT_PATH=report, TRAJECTORY_PATH=trajectory, AUDIT_PATH=audit_path), \
                        patch.object(VERIFY.subprocess, "run", side_effect=retrieval), \
                        patch.object(VERIFY, "stop_submission_processes", side_effect=lambda: events.append("stopped")), \
                        patch.object(VERIFY, "run_audit", side_effect=audit) as judge, patch("builtins.print"):
                    status = VERIFY.main()
                self.assertEqual(float((root / "reward.txt").read_text()), 0.7 if mode == "pass" else 0)
                self.assertEqual(status, 0 if mode in ("pass", "reject") else 1)
                self.assertEqual(judge.call_count, 0 if mode == "missing-trajectory" else 1)

    def test_audit_uses_private_output_and_phase_scoped_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private"
            audit = private / "judge-reward.json"
            private.mkdir()
            audit.write_text('{"jailbreak_judge": 1}')  # stale success must be removed
            with patch.multiple(VERIFY, RESULTS_DIR=root, PRIVATE_DIR=private, AUDIT_PATH=audit), \
                    patch.dict(os.environ, {"OPENAI_API_KEY": "judge-fixture", "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
                                            "OPENROUTER_API_KEY": "submission-fixture", "OTHER_SECRET": "unused"}, clear=True), \
                    patch.object(VERIFY.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertEqual(VERIFY.run_audit(), 0)
            self.assertFalse(audit.exists())
            command = run.call_args_list[1].args[0]
            self.assertEqual(command[0], "/usr/bin/timeout")
            self.assertIn("3600s", command)
            self.assertEqual(command[command.index("--output") + 1], str(audit))
            env = run.call_args_list[1].kwargs["env"]
            self.assertEqual(env["OPENAI_API_KEY"], "judge-fixture")
            self.assertNotIn("OPENROUTER_API_KEY", env)
            self.assertNotIn("OTHER_SECRET", env)


if __name__ == "__main__":
    unittest.main()
