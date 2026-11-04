"""Offline evidence-gated repeated answer judging and failure propagation."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import json
import unittest
from unittest.mock import patch

import grader


class AnswerRepeatTests(unittest.TestCase):
    def run_grade(self, responses, evidence="doc"):
        queries = [{"query_id": "q", "question": "question"}]
        gold = {"q": {"evidence": "doc", "answer": "reference"}}
        prediction = {"q": {"evidence": evidence, "answer": "fixed answer"}}
        with patch.object(grader, "load_reference_data", return_value=(queries, gold, {"doc"})), \
                patch.object(grader, "load_predictions", return_value=prediction), \
                patch.object(grader, "judge_config", return_value=grader.JudgeConfig("base", "key", "model")), \
                patch.object(grader, "call_judge", side_effect=responses) as judge, \
                patch.object(grader, "write_report") as write, \
                patch.object(grader, "EXECUTION_ERROR", ""):
            status = grader.main()
        return status, write.call_args.args[0], judge

    def test_averages_three_decisions_without_majority_vote(self):
        values = [json.dumps({"correct": value}) for value in [True, True, False]]
        status, report, judge = self.run_grade(values)
        self.assertEqual(status, 0)
        self.assertTrue(report["valid"])
        self.assertAlmostEqual(report["primary_metric"]["value"], 2 / 3)
        self.assertEqual(judge.call_count, 3)
        self.assertEqual(len(report["per_query_metrics"][0]["judge_samples"]), 3)
        self.assertTrue(all(call.kwargs["candidate_answer"] == "fixed answer" for call in judge.call_args_list))

    def test_wrong_evidence_never_calls_answer_judge(self):
        status, report, judge = self.run_grade([], evidence="wrong")
        self.assertEqual(status, 0)
        self.assertEqual(report["primary_metric"]["value"], 0)
        judge.assert_not_called()

    def test_partial_or_malformed_judging_invalidates_measurement(self):
        for last in [RuntimeError("judge unavailable"), "malformed"]:
            with self.subTest(last=last):
                status, report, judge = self.run_grade(['{"correct":true}', last])
                self.assertEqual(status, 1)
                self.assertFalse(report["valid"])
                self.assertEqual(report["primary_metric"]["value"], 0)
                self.assertEqual(report["answer_judge_call_count"], 2)
                self.assertTrue(report["errors"])


if __name__ == "__main__":
    unittest.main()
