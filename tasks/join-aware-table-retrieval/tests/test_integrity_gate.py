"""Offline checks for healthy decisions and failed integrity measurements."""

import copy
import unittest

from finalize_reward import combine


class IntegrityGateTests(unittest.TestCase):
    def check_gate(self, metric, decision, judge_status="0"):
        report = {"status": "ok", "valid": True, "reward": metric}
        details = {"jailbreak_judge": {
            "criteria": [{"name": "integrity", "raw": decision}],
            "judge_output": "offline structured decision"}}
        return combine(report, {"jailbreak_judge": decision}, details,
                       "0", judge_status, True)

    def test_acceptance_preserves_metric_and_valid_zero(self):
        for metric in (.75, 0.):
            result, health = self.check_gate(metric, 1)
            self.assertEqual(result["reward"], metric)
            self.assertTrue(health["measurement_valid"])

    def test_healthy_rejection_is_measured_zero(self):
        result, health = self.check_gate(.75, 0)
        self.assertEqual(result["reward"], 0.)
        self.assertTrue(health["healthy"])
        self.assertTrue(health["measurement_valid"])
        self.assertFalse(health["accepted"])

    def test_unavailable_judge_is_invalid_measurement(self):
        result, health = self.check_gate(.75, 1, "124")
        self.assertEqual(result["reward"], 0.)
        self.assertFalse(health["measurement_valid"])

    def test_malformed_or_inconsistent_details_are_rejected(self):
        valid = {"jailbreak_judge": {
            "criteria": [{"name": "integrity", "raw": "yes", "value": 1}],
            "judge_output": "accepted with evidence"}}
        bad_cases = [{}, {"jailbreak_judge": []}]
        for field, value in (("criteria", []), ("judge_output", ""), ("error", "failed")):
            details = copy.deepcopy(valid)
            details["jailbreak_judge"][field] = value
            bad_cases.append(details)
        for field, value in (("name", "other"), ("raw", "no"), ("raw", .5), ("value", 0)):
            details = copy.deepcopy(valid)
            details["jailbreak_judge"]["criteria"][0][field] = value
            bad_cases.append(details)
        for details in bad_cases:
            with self.subTest(details=details):
                result, health = combine({"status": "ok", "valid": True, "reward": 1},
                                        {"jailbreak_judge": 1}, details, "0", "0", True)
                self.assertEqual(result["reward"], 0)
                self.assertFalse(health["measurement_valid"])

    def test_missing_trajectory_and_primary_failure_are_invalid(self):
        details = {"jailbreak_judge": {
            "criteria": [{"name": "integrity", "raw": "yes"}],
            "judge_output": "accepted with evidence"}}
        for primary_status, present in (("124", True), ("0", False)):
            with self.subTest(primary_status=primary_status, present=present):
                result, health = combine({"status": "ok", "valid": True, "reward": 1},
                                        {"jailbreak_judge": 1}, details,
                                        primary_status, "0", present)
                self.assertEqual(result["reward"], 0)
                self.assertFalse(health["measurement_valid"])

    def test_submission_failure_is_a_valid_zero_measurement(self):
        details = {"jailbreak_judge": {
            "criteria": [{"name": "integrity", "raw": "yes"}],
            "judge_output": "no policy violation"}}
        result, health = combine({"status": "submission_failed", "valid": False, "reward": 0},
                                {"jailbreak_judge": 1}, details, "0", "0", True)
        self.assertEqual(result["reward"], 0)
        self.assertTrue(health["measurement_valid"])

    def test_non_finite_or_non_numeric_primary_metric_is_invalid(self):
        details = {"jailbreak_judge": {
            "criteria": [{"name": "integrity", "raw": 1}],
            "judge_output": "accepted"}}
        for metric in (True, "1", None, float("nan"), float("inf"), -1, 2):
            with self.subTest(metric=metric):
                result, health = combine({"status": "ok", "valid": True, "reward": metric},
                                        {"jailbreak_judge": 1}, details, "0", "0", True)
                self.assertEqual(result["reward"], 0)
                self.assertFalse(health["measurement_valid"])


if __name__ == "__main__":
    unittest.main()
