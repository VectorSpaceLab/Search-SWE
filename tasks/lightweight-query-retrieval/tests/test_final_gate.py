"""Offline gate checks; supplied judge decisions do not test an LLM's detection."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_reward as finalizer
import grader


class FinalGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report.json"
        self.judge = self.root / "judge.json"
        self.trajectory = self.root / "trajectory.json"
        self.evaluation = {"task_id": "lightweight-query-retrieval", "valid": True,
                           "query_count": 1271, "reward": 0.375}
        self.report.write_text(json.dumps(self.evaluation))
        self.judge.write_text('{"jailbreak_judge":1}')
        self.trajectory.write_text('{"steps":[{"source":"agent","message":"build retrieval"}]}')
        for key, value in {"REWARD_DIR": self.root, "EVALUATION_PATH": self.report,
                           "JUDGE_PATH": self.judge, "TRAJECTORY_PATH": self.trajectory}.items():
            stub = patch.object(finalizer, key, value)
            stub.start()
            self.addCleanup(stub.stop)
        env = patch.dict(os.environ, {"SEARCH_SWE_GRADER_STATUS": "0", "SEARCH_SWE_JUDGE_STATUS": "0"})
        env.start()
        self.addCleanup(env.stop)

    def finish(self, expected, healthy=True):
        with contextlib.redirect_stdout(io.StringIO()):
            status = finalizer.main()
        self.assertEqual(status, 0 if healthy else 1)
        result = json.loads((self.root / "reward.json").read_text())
        self.assertEqual(result["reward"], expected)
        self.assertAlmostEqual(float((self.root / "reward.txt").read_text()), expected, places=9)
        self.assertTrue(all(type(value) in (int, float) for value in result.values()))
        return json.loads((self.root / "reward-details.json").read_text())["final_gate"]

    def test_pass_preserves_raw_fractional_and_zero_scores(self):
        for score in (0.0, 0.375, 0.4273553649, 1.0):
            with self.subTest(score=score):
                self.report.write_text(json.dumps({**self.evaluation, "reward": score}))
                self.finish(score)

    def test_integrity_rejection_cannot_be_overridden_by_good_retrieval(self):
        # This represents the decision on a prohibited answer-table submission.
        # It checks enforcement of no, not whether a real judge recognizes it.
        self.judge.write_text('{"jailbreak_judge":0,"reward":1}')
        details = self.finish(0.0)
        self.assertEqual(details["retrieval_reward"], 0.375)
        self.assertTrue(details["judge_output_valid"])

    def test_nonbinary_and_malformed_judge_outputs_fail_closed(self):
        cases = [json.dumps({"jailbreak_judge": value}) for value in
                 (0.5, 2, -1, "1", True, False, None, {}, [], float("nan"), float("inf"))]
        cases += ['{}', '[]', 'not JSON', '{"jailbreak_judge":0,"jailbreak_judge":1}']
        for payload in cases:
            with self.subTest(payload=payload):
                self.judge.write_text(payload)
                self.assertFalse(self.finish(0.0, False)["judge_output_valid"])
        self.judge.unlink()
        self.finish(0.0, False)

    def test_failed_grader_or_judge_cannot_release_stale_pass(self):
        for key in ("SEARCH_SWE_GRADER_STATUS", "SEARCH_SWE_JUDGE_STATUS"):
            for status in ("", "1", "78", "124", "137"):
                with self.subTest(key=key, status=status), patch.dict(os.environ, {key: status}):
                    self.finish(0.0, False)

    def test_trajectory_must_be_present_regular_and_valid(self):
        for payload in ("", "{}", "[]", "invalid"):
            with self.subTest(payload=payload):
                self.trajectory.write_text(payload)
                self.finish(0.0, False)
        self.trajectory.unlink()
        self.finish(0.0, False)
        self.trajectory.symlink_to(self.report)
        self.finish(0.0, False)

    def test_invalid_primary_report_cannot_be_rescued_by_judge(self):
        changes = [{"valid": False}, {"valid": "true"}, {"query_count": 1},
                   {"task_id": "other"}]
        changes += [{"reward": value} for value in
                    (True, "0.5", None, -0.1, 1.1, 10 ** 1000, float("nan"), float("inf"))]
        for change in changes:
            with self.subTest(change=str(change)[:100]):
                self.report.write_text(json.dumps({**self.evaluation, **change}))
                self.finish(0.0, False)
        self.report.unlink()
        self.finish(0.0, False)

    def test_primary_grader_keeps_public_reward_zero_before_audit(self):
        with patch.object(grader, "LOGS", self.root), \
                patch.object(grader, "evaluate", return_value=copy.deepcopy(self.evaluation)), \
                contextlib.redirect_stdout(io.StringIO()):
            grader.main()
        self.assertEqual(json.loads(self.report.read_text())["reward"], 0.375)
        self.assertEqual(json.loads((self.root / "reward.json").read_text())["reward"], 0)
        self.assertEqual(float((self.root / "reward.txt").read_text()), 0)


if __name__ == "__main__":
    unittest.main()
