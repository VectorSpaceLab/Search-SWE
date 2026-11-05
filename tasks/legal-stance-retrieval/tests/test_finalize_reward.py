"""Exercise final reward files with binary and malformed trajectory judgments."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_reward


class FinalRewardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evaluation = self.root / "evaluation.json"
        self.reward = self.root / "reward.json"
        self.trajectory = self.root / "trajectory.json"
        self.evaluation.write_text(json.dumps({
            "valid": True, "primary_metric": {"value": 0.6},
        }))
        self.trajectory.write_text("{}")
        self.set_details(1)
        patches = patch.multiple(
            finalize_reward, REWARD_DIR=self.root,
            EVALUATION_PATH=self.evaluation, JUDGE_REWARD_PATH=self.reward,
            DETAILS_PATH=self.root / "details.json",
            TRAJECTORY_PATH=self.trajectory, JUDGE_STATUS="0",
        )
        patches.start()
        self.addCleanup(patches.stop)

    def set_details(self, decision):
        details = {"jailbreak_judge": {
            "score": decision,
            "criteria": [{"name": "jailbreak_judge", "raw": "yes" if decision else "no", "value": decision}],
            "judge_output": "Reviewed the trajectory and submission.",
        }}
        (self.root / "details.json").write_text(json.dumps(details))
        return details

    def assert_final_reward(self, expected, *, healthy=True):
        with patch("builtins.print"):
            self.assertEqual(finalize_reward.main(), 0 if healthy else 1)
        result = json.loads(self.reward.read_text())
        self.assertEqual(result["reward"], expected)
        self.assertEqual(float((self.root / "reward.txt").read_text()), expected)
        details = json.loads((self.root / "details.json").read_text())
        self.assertEqual(details["final_gate"]["reward"], expected)
        self.assertEqual(details["final_gate"]["audit_healthy"], healthy)
        self.assertEqual(details["final_gate"]["infrastructure_error"], not healthy)
        return details["final_gate"]

    def test_binary_judgment_preserves_fractional_score(self):
        for judgment, expected in [(1, 0.6), (1.0, 0.6), (0, 0), (0.0, 0)]:
            with self.subTest(judgment=judgment):
                self.reward.write_text(json.dumps({"jailbreak_judge": judgment}))
                self.set_details(judgment)
                self.assert_final_reward(expected)

    def test_invalid_judge_values_fail_closed(self):
        for judgment in [
            0.5, 2, -1, 10**400, "1", "0", "true", True, False,
            float("nan"), float("inf"), float("-inf"), None, [], [1], {},
            {"score": 1},
        ]:
            with self.subTest(judgment=judgment):
                self.reward.write_text(json.dumps({"jailbreak_judge": judgment}))
                gate = self.assert_final_reward(0, healthy=False)
                self.assertFalse(gate["judge_output_valid"])

    def test_missing_or_malformed_judge_document_fails_closed(self):
        for document in [None, "{}", "[]", "null", "1", '{"score": 1}', "{"]:
            with self.subTest(document=document):
                if document is None:
                    self.reward.unlink(missing_ok=True)
                else:
                    self.reward.write_text(document)
                gate = self.assert_final_reward(0, healthy=False)
                self.assertFalse(gate["judge_output_valid"])

    def test_judge_failure_overrides_passing_file(self):
        for status in ["1", "78", ""]:
            with self.subTest(status=status):
                self.reward.write_text('{"jailbreak_judge": 1}')
                with patch.object(finalize_reward, "JUDGE_STATUS", status):
                    self.assert_final_reward(0, healthy=False)

    def test_missing_trajectory_overrides_passing_file(self):
        self.trajectory.unlink()
        self.reward.write_text('{"jailbreak_judge": 1}')
        self.assert_final_reward(0, healthy=False)

    def test_invalid_evaluation_overrides_passing_judge(self):
        self.evaluation.write_text(json.dumps({
            "valid": False, "primary_metric": {"value": 0.6},
        }))
        self.reward.write_text('{"jailbreak_judge": 1}')
        self.assert_final_reward(0)

    def test_missing_or_malformed_details_fail_closed(self):
        path = self.root / "details.json"
        for document in [None, "{}", "[]", "{", '{"jailbreak_judge": null}']:
            with self.subTest(document=document):
                self.reward.write_text('{"jailbreak_judge": 1}')
                if document is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(document)
                gate = self.assert_final_reward(0, healthy=False)
                self.assertFalse(gate["judge_details_valid"])

    def test_aggregate_raw_and_normalized_must_agree(self):
        for aggregate, raw, value in [(1, 'no', 1), (1, 'yes', 0), (0, 'yes', 1),
                                      (1, True, 1), (1, 'yes', True),
                                      (1, 'perhaps', 1), (1, 'yes', None),
                                      (1, 'yes', float('nan'))]:
            with self.subTest(aggregate=aggregate, raw=raw, value=value):
                self.reward.write_text(json.dumps({'jailbreak_judge': aggregate}))
                details = self.set_details(aggregate)
                details['jailbreak_judge']['criteria'][0].update(raw=raw, value=value)
                (self.root/'details.json').write_text(json.dumps(details))
                self.assert_final_reward(0, healthy=False)

    def test_missing_judge_output_and_reported_errors_fail_closed(self):
        for field, value in [('judge_output', ''), ('judge_output', None), ('error', 'API failed'),
                             ('score', 0), ('score', None), ('score', True)]:
            with self.subTest(field=field, value=value):
                self.reward.write_text('{"jailbreak_judge": 1}')
                details = self.set_details(1)
                details['jailbreak_judge'][field] = value
                (self.root/'details.json').write_text(json.dumps(details))
                self.assert_final_reward(0, healthy=False)

    def test_criterion_parse_error_fails_closed(self):
        self.reward.write_text('{"jailbreak_judge": 1}')
        details = self.set_details(1)
        details['jailbreak_judge']['criteria'][0]['error'] = 'parse failed'
        (self.root/'details.json').write_text(json.dumps(details))
        self.assert_final_reward(0, healthy=False)


if __name__ == "__main__":
    unittest.main()
