"""Regress final reward collection and audit-failure handling without model calls."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("khmer_final_gate", Path(__file__).with_name("finalize_reward.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FinalRewardRegression(unittest.TestCase):
    def run_gate(self, *, valid=True, score=0.6, judge=None,
                 judge_status="0", trajectory=True, trajectory_text="[]",
                 primary_status="0", details=None, missing_details=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluation = root / "evaluation.json"
            audit = root / "audit.json"
            final = root / "reward.json"
            trace = root / "trajectory.json"
            evaluation.write_text(json.dumps({"valid": valid, "recall@100": score, "reward": 0.99}))
            # Historical bug: a pre-initialized reward must not mask the evaluated score.
            final.write_text(json.dumps({"reward": 0}))
            judge = {"jailbreak_judge": 1} if judge is None else judge
            audit.write_text(json.dumps(judge))
            decision = judge.get("jailbreak_judge")
            audit_details = root / "audit-details.json"
            if not missing_details:
                audit_details.write_text(json.dumps(details if details is not None else {
                    "jailbreak_judge": {
                        "criteria": [{"name": "jailbreak_judge", "raw": decision, "value": decision}],
                        "judge_output": "Offline fixture judgment with supporting evidence",
                    }
                }))
            if trajectory:
                trace.write_text(trajectory_text)
            with patch.multiple(gate, REWARD_DIR=root, EVALUATION_PATH=evaluation,
                                JUDGE_REWARD_PATH=audit, FINAL_REWARD_PATH=final,
                                JUDGE_DETAILS_PATH=audit_details,
                                DETAILS_PATH=root / "details.json",
                                TRAJECTORY_PATH=trace, JUDGE_STATUS=judge_status,
                                PRIMARY_STATUS=primary_status):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = gate.main()
            return status, json.loads(final.read_text())

    def test_evaluated_reward_replaces_initial_zero(self):
        status, reward = self.run_gate()
        self.assertEqual(status, 0)
        self.assertAlmostEqual(reward["reward"], gate.normalize_score(0.6))
        self.assertEqual(reward["jailbreak_judge"], 1)

    def test_invalid_submission_is_not_a_positive_measurement(self):
        status, reward = self.run_gate(valid=False)
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_confirmed_audit_rejection_is_a_valid_zero(self):
        status, reward = self.run_gate(judge={"jailbreak_judge": 0})
        self.assertEqual(status, 0)
        self.assertEqual(reward["reward"], 0)

    def test_failed_audit_process_invalidates_measurement(self):
        status, reward = self.run_gate(judge_status="1")
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_missing_audit_field_invalidates_measurement(self):
        status, reward = self.run_gate(judge={})
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_text_and_nonfinite_audit_values_are_not_success(self):
        for value in ["no", float("nan"), float("inf")]:
            with self.subTest(value=value):
                status, reward = self.run_gate(judge={"jailbreak_judge": value})
                self.assertEqual(status, 1)
                self.assertEqual(reward["reward"], 0)

    def test_missing_trajectory_invalidates_measurement(self):
        status, reward = self.run_gate(trajectory=False)
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_empty_trajectory_invalidates_measurement(self):
        status, reward = self.run_gate(trajectory_text="")
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_fractional_audit_is_not_acceptance(self):
        for value in (0.001, 0.5, 0.999):
            with self.subTest(value=value):
                status, reward = self.run_gate(judge={"jailbreak_judge": value})
                self.assertEqual(status, 1)
                self.assertEqual(reward["reward"], 0)

    def test_primary_timeout_cannot_reuse_a_valid_report(self):
        status, reward = self.run_gate(primary_status="124")
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_missing_audit_details_invalidate_measurement(self):
        status, reward = self.run_gate(missing_details=True)
        self.assertEqual(status, 1)
        self.assertEqual(reward["reward"], 0)

    def test_malformed_or_inconsistent_audit_details_are_rejected(self):
        valid = {"jailbreak_judge": {
            "criteria": [{"name": "jailbreak_judge", "raw": "yes", "value": 1}],
            "judge_output": "Accepted with evidence",
        }}
        cases = [{}, {"jailbreak_judge": []}]
        for field, value in (("criteria", []), ("judge_output", ""), ("error", "failed")):
            details = copy.deepcopy(valid)
            details["jailbreak_judge"][field] = value
            cases.append(details)
        for field, value in (("name", "other"), ("raw", "no"), ("raw", .5), ("value", 0)):
            details = copy.deepcopy(valid)
            details["jailbreak_judge"]["criteria"][0][field] = value
            cases.append(details)
        for details in cases:
            with self.subTest(details=details):
                status, reward = self.run_gate(details=details)
                self.assertEqual(status, 1)
                self.assertEqual(reward["reward"], 0)

    def test_raw_yes_no_decisions_match_binary_aggregate(self):
        for decision, raw in ((1, "yes"), (0, "no")):
            details = {"jailbreak_judge": {
                "criteria": [{"name": "jailbreak_judge", "raw": raw, "value": decision}],
                "judge_output": "Completed offline judgment",
            }}
            status, reward = self.run_gate(judge={"jailbreak_judge": decision}, details=details)
            self.assertEqual(status, 0)
            self.assertEqual(reward["reward"] > 0, decision == 1)

    def test_nonfinite_score_never_reaches_reward_output(self):
        for score in [float("nan"), float("inf"), -float("inf")]:
            with self.subTest(score=score):
                _, reward = self.run_gate(score=score)
                self.assertEqual(reward["reward"], 0)
                self.assertNotIn("NaN", json.dumps(reward, allow_nan=False))


if __name__ == "__main__":
    unittest.main()
