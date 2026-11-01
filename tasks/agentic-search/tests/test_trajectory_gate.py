"""Offline tests for the agentic-search trajectory reward gate."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


GATES = [Path(__file__).with_name("trajectory_gate.py")]


def load(path):
    spec = importlib.util.spec_from_file_location("trajectory_gate_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TrajectoryGate(unittest.TestCase):
    def test_real_rewardkit_leaf_discovery_and_output_contract(self):
        # Mock the judge transport, while using installed RewardKit 0.2.0 to
        # discover the actual rubric, normalize scores, aggregate and serialize.
        with patch.dict(os.environ, {"LITELLM_LOCAL_MODEL_COST_MAP": "true"}):
            from importlib.metadata import version
            from rewardkit import reward as reward_module, runner
            from rewardkit.models import AgentJudgeResult, Score
            self.assertEqual(version("harbor-rewardkit"), "0.2.0")
            load(GATES[0].with_name("rewardkit_deepseek.py"))

        for raw in ("yes", "no"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tests = root / "tests"
                audit = tests / "jailbreak_judge"
                audit.mkdir(parents=True)
                shutil.copyfile(GATES[0].parent / "jailbreak_judge/codex.toml", audit / "codex.toml")
                (tests / "verifier_helper.py").write_text("raise AssertionError('verifier helper imported')\n")
                logs = root / "logs"
                logs.mkdir()
                (logs / "task-score.txt").write_text("0.7")
                trajectory = root / "trajectory.json"
                trajectory.write_text('{"steps":[{"source":"agent","step_id":1}]}')
                module = load(GATES[0])

                async def judge_transport(judge, criteria, weights, **kwargs):
                    self.assertEqual(judge.agent, "deepseek-codex")
                    self.assertEqual([c.name for c in criteria], ["jailbreak_judge"])
                    scores = [Score(name=c.name, value=c.output_format.normalize(raw), raw=raw, weight=w)
                              for c, w in zip(criteria, weights)]
                    return AgentJudgeResult(scores=scores, output="Offline transport fixture", warnings=[])

                def execute_rewardkit(command, **kwargs):
                    self.assertEqual(Path(command[2]), audit)
                    output = Path(command[command.index("--output") + 1])
                    runner.run(command[2], workspace=root, output=output)
                    process = unittest.mock.Mock(pid=12345)
                    process.wait.return_value = 0
                    return process

                env = {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1", "OPENAI_API_KEY": "offline-placeholder",
                       "LITELLM_LOCAL_MODEL_COST_MAP": "true"}
                with patch.dict(os.environ, env, clear=True), \
                        patch.object(reward_module, "arun_agent", side_effect=judge_transport), \
                        patch.object(runner, "_import_py_file", side_effect=AssertionError("helper import attempted")), \
                        patch.object(module.subprocess, "Popen", side_effect=execute_rewardkit), \
                        patch.object(module.os, "killpg"):
                    self.assertEqual(module.apply_gate(logs, trajectory, tests, root), 0)
                expected = 1.0 if raw == "yes" else 0.0
                actual = json.loads((logs / "jailbreak-result.json").read_text())
                self.assertEqual(actual, {"reward": expected})
                detail = json.loads((logs / "reward-details.json").read_text())
                self.assertEqual(detail["reward"]["criteria"][0]["raw"], raw)
                self.assertEqual(json.loads((logs / "reward.json").read_text())["reward"], 0.7 * expected)

    def test_success_violation_and_fail_closed_errors(self):
        paths = GATES
        self.assertTrue(paths)
        cases = [
            ("pass", {"reward": 1}, 0, 0.7),
            ("violation", {"reward": 0}, 0, 0.0),
            ("zero-score", {"reward": 1}, 0, 0.0),
            ("fractional", {"reward": 0.5}, 1, 0.0),
            ("nan", {"reward": float("nan")}, 1, 0.0),
            ("string", {"reward": "1"}, 1, 0.0),
            ("missing-result", {}, 1, 0.0),
            ("unexpected-field", {"jailbreak_judge": 1}, 1, 0.0),
            ("malformed-result", None, 1, 0.0),
            ("no-output", None, 1, 0.0),
            ("failed-process", {"reward": 1}, 1, 0.0),
            ("timeout", None, 1, 0.0),
            ("missing-trajectory", None, 1, 0.0),
            ("empty-trajectory", None, 1, 0.0),
            ("malformed-trajectory", None, 1, 0.0),
            ("missing-key", None, 1, 0.0),
            ("invalid-score", None, 1, 0.0),
        ]
        for path in paths:
            module = load(path)
            for name, result, expected_status, expected_reward in cases:
                with self.subTest(path=path, case=name), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    score = "nan" if name == "invalid-score" else "0" if name == "zero-score" else "0.7"
                    (root / "task-score.txt").write_text(score)
                    trajectory = root / "trajectory.json"
                    trajectory.write_text(json.dumps({"steps": [{"step_id": 1, "source": "agent"}]}))
                    if name == "missing-trajectory":
                        trajectory.unlink()
                    elif name == "empty-trajectory":
                        trajectory.write_text('{"steps": []}')
                    elif name == "malformed-trajectory":
                        trajectory.write_text('{')
                    # Stale success must never survive a failed judge invocation.
                    (root / "jailbreak-result.json").write_text('{"reward": 1}')
                    (root / "reward.txt").write_text("1")

                    def judge(tests, workspace, output, logs):
                        self.assertEqual(float((logs / "reward.txt").read_text()), 0)
                        self.assertFalse(output.exists())
                        if name == "timeout":
                            raise subprocess.TimeoutExpired("fixture", 1)
                        if name != "no-output":
                            output.write_text("{" if name == "malformed-result" else json.dumps(result))
                        return 1 if name == "failed-process" else 0

                    env = {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1", "OPENAI_API_KEY": "fixture"}
                    if name == "missing-key":
                        env.pop("OPENAI_API_KEY")
                    with patch.dict(os.environ, env, clear=True), patch.object(module, "run_judge", side_effect=judge):
                        status = module.apply_gate(root, trajectory, root, root)
                    reward = json.loads((root / "reward.json").read_text())
                    self.assertEqual(status, expected_status)
                    self.assertIn("gold_recall_at_5", reward)
                    self.assertEqual(reward["reward"], expected_reward)
                    self.assertEqual(float((root / "reward.txt").read_text()), expected_reward)
                    self.assertTrue(all(isinstance(value, (int, float)) for value in reward.values()))

    def test_judge_timeout_kills_process_group(self):
        module = load(GATES[0])
        with tempfile.TemporaryDirectory() as directory, patch.object(module.subprocess, "Popen") as start, \
                patch.object(module.os, "killpg") as kill:
            start.return_value.pid = 12345
            start.return_value.wait.side_effect = [subprocess.TimeoutExpired("fixture", 1230), -9]
            root = Path(directory)
            with self.assertRaises(subprocess.TimeoutExpired):
                module.run_judge(root, root, root / "output.json", root)
            self.assertTrue(start.call_args.kwargs["start_new_session"])
            kill.assert_called_once_with(12345, module.signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
