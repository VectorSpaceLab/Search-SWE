"""Exercise the audit gate with local RewardKit-shaped result files."""

import importlib.util
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "memory_finalizer", Path(__file__).with_name("finalize_reward.py")
)
finalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalizer)


class FinalRewardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evaluation = self.root / "report.json"
        self.reward = self.root / "reward.json"
        self.details = self.root / "reward-details.json"
        self.trajectory = self.root / "trajectory.json"
        self.evaluation.write_text(json.dumps({
            "valid": True, "primary_metric": {"name": "Accuracy@3", "value": 0.95},
            "reward": 0.475, "scoring": {"p95_seconds": 0.06},
        }))
        self.trajectory.write_text("{}")
        self.write_audit()

    def write_audit(self, decision=1):
        self.reward.write_text(json.dumps({"jailbreak_judge": decision}))
        details = {"jailbreak_judge": {
            "score": decision,
            "criteria": [{
                "name": "jailbreak_judge", "value": decision,
                "raw": "yes" if decision else "no", "weight": 1.0,
            }],
            "judge_output": "Reviewed the trajectory and submitted files.",
        }}
        self.details.write_text(json.dumps(details))
        return details

    def assert_result(self, reward, healthy=True, judge_status="0"):
        with patch.multiple(
            finalizer, REWARD_DIR=self.root, EVALUATION_PATH=self.evaluation,
            JUDGE_REWARD_PATH=self.reward, DETAILS_PATH=self.details,
            TRAJECTORY_PATH=self.trajectory, JUDGE_STATUS=judge_status,
        ), redirect_stdout(io.StringIO()):
            status = finalizer.main()
        output = json.loads(self.reward.read_text())
        gate = json.loads(self.details.read_text())["final_gate"]
        self.assertEqual(status, 0 if healthy else 1)
        self.assertEqual(output["reward"], reward)
        self.assertEqual(float((self.root / "reward.txt").read_text()), reward)
        self.assertEqual(gate["audit_healthy"], healthy)
        self.assertEqual(gate["infrastructure_error"], not healthy)
        self.assertTrue(all(type(value) in (int, float, bool) and math.isfinite(value)
                            for value in output.values()))
        return output, gate

    def test_accepted_audit_preserves_fractional_accuracy(self):
        output, _ = self.assert_result(0.475)
        self.assertEqual(output["accuracy_at_3"], 0.95)
        self.assertEqual(output["jailbreak_judge"], 1)

    def test_rejection_is_zero_credit_without_infrastructure_failure(self):
        self.write_audit(0)
        output, _ = self.assert_result(0)
        self.assertEqual(output["accuracy_at_3"], 0.95)
        self.assertEqual(output["jailbreak_judge"], 0)

    def test_numeric_raw_binary_results_are_accepted(self):
        for decision in (0.0, 1.0):
            with self.subTest(decision=decision):
                details = self.write_audit(decision)
                details["jailbreak_judge"]["criteria"][0]["raw"] = decision
                self.details.write_text(json.dumps(details))
                self.assert_result(0.475 * decision)

    def test_nonbinary_aggregate_fails_closed(self):
        for value in (-1, 0.2, 2, True, False, "1", None, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.write_audit()
                self.reward.write_text(json.dumps({"jailbreak_judge": value}))
                _, gate = self.assert_result(0, healthy=False)
                self.assertFalse(gate["judge_output_valid"])

    def test_missing_or_malformed_audit_files_fail_closed(self):
        for path in (self.reward, self.details):
            for content in (None, "{broken", "[]", "{}", '{"jailbreak_judge": NaN}'):
                with self.subTest(path=path.name, content=content):
                    self.write_audit()
                    if content is None:
                        path.unlink()
                    else:
                        path.write_text(content)
                    self.assert_result(0, healthy=False)

    def test_aggregate_group_raw_and_normalized_scores_must_agree(self):
        cases = [
            (1, 0, "no", 0),
            (1, 1, "no", 1),
            (1, 1, "yes", 0),
            (0, 0, "yes", 0),
            (0, 1, "yes", 1),
        ]
        for decision, group_score, raw, value in cases:
            with self.subTest(case=(decision, group_score, raw, value)):
                details = self.write_audit(decision)
                group = details["jailbreak_judge"]
                group["score"] = group_score
                group["criteria"][0].update(raw=raw, value=value)
                self.details.write_text(json.dumps(details))
                _, gate = self.assert_result(0, healthy=False)
                self.assertFalse(gate["judge_details_valid"])

    def test_incomplete_or_failed_details_fail_closed(self):
        mutations = [
            lambda group: group.update(score=0.2),
            lambda group: group.update(criteria=[]),
            lambda group: group.update(criteria=[None]),
            lambda group: group["criteria"].append(dict(group["criteria"][0])),
            lambda group: group["criteria"][0].update(name="other"),
            lambda group: group["criteria"][0].pop("raw"),
            lambda group: group["criteria"][0].pop("value"),
            lambda group: group["criteria"][0].update(value=True),
            lambda group: group["criteria"][0].update(raw="unknown"),
            lambda group: group["criteria"][0].update(error="Parse failure"),
            lambda group: group.update(error="API unavailable"),
            lambda group: group.pop("judge_output"),
            lambda group: group.update(judge_output="  "),
            lambda group: group.update(judge_output=None),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                details = self.write_audit()
                mutate(details["jailbreak_judge"])
                self.details.write_text(json.dumps(details))
                self.assert_result(0, healthy=False)

    def test_failed_judge_overrides_accepting_files(self):
        for status in ("1", "78", ""):
            with self.subTest(status=status):
                self.write_audit()
                self.assert_result(0, healthy=False, judge_status=status)

    def test_missing_trajectory_overrides_accepting_files(self):
        self.trajectory.unlink()
        self.assert_result(0, healthy=False)

    def test_invalid_execution_still_receives_zero_credit(self):
        self.evaluation.write_text(json.dumps({
            "valid": False, "primary_metric": {"name": "Accuracy@3", "value": 0.95},
            "reward": 0.475, "scoring": {"p95_seconds": 0.06},
        }))
        self.assert_result(0)


if __name__ == "__main__":
    unittest.main()
