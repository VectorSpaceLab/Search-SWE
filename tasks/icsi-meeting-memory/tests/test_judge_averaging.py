"""Repeated grading uses fixed outputs and preserves fractional joint scores."""

import unittest
from unittest.mock import patch

from harness import grade_answer, grade_evidence, joint_accuracy


class JudgeAveragingTests(unittest.TestCase):
    def test_same_answer_is_judged_three_times_and_averaged(self):
        with patch("harness.llm", side_effect=[
            ({"correct": value}, {}) for value in (True, True, False)
        ]) as model:
            result = grade_answer(
                {"query_id": "q", "question": "Why?"},
                {"answer": "Cost", "criteria": ["Budget was insufficient"]},
                {"answer": "It exceeded the budget."},
            )
        self.assertAlmostEqual(result["correct"], 2 / 3)
        self.assertEqual(model.call_count, 3)
        self.assertTrue(all(call.args == model.call_args_list[0].args
                            for call in model.call_args_list))

    def test_failed_third_answer_judgment_is_not_dropped(self):
        with patch("harness.llm", side_effect=[
            ({"correct": True}, {}), ({"correct": True}, {}),
            RuntimeError("judge unavailable"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                grade_answer(
                    {"query_id": "q", "question": "Why?"},
                    {"answer": "Cost", "criteria": ["Budget"]},
                    {"answer": "Cost"},
                )

    def test_fixed_extraction_and_three_complete_evidence_decisions(self):
        citation = {"memory_index": 0, "quote": "Budget was insufficient."}
        positive = {"hit": True, "matches": [
            {"passage_index": 0, "reference_fact": "Insufficient budget"}
        ]}
        with patch("harness.llm", side_effect=[
            ({"citations": [citation]}, {}),
            (positive, {}), ({"supported": True}, {}),
            (positive, {}), ({"supported": False}, {}),
            (positive, {}), ({"supported": True}, {}),
        ]) as model:
            result = grade_evidence(
                {"question": "Why?"}, [{"text": "It was too costly."}],
                ["Budget was insufficient."],
            )
        self.assertAlmostEqual(result["hit"], 2 / 3)
        extractions = [call for call in model.call_args_list
                       if "retrieved_texts" in call.args[1]]
        comparisons = [call for call in model.call_args_list
                       if "retrieved_passages" in call.args[1]]
        self.assertEqual(len(extractions), 1)
        self.assertEqual(len(comparisons), 3)
        self.assertTrue(all(call.args == comparisons[0].args for call in comparisons))
        self.assertEqual([vote["hit"] for vote in result["votes"]], [True, False, True])

    def test_failed_third_evidence_judgment_invalidates_measurement(self):
        positive = {"hit": True, "matches": [
            {"passage_index": 0, "reference_fact": "Cost"}
        ]}
        with patch("harness.llm", side_effect=[
            ({"citations": [{"memory_index": 0, "quote": "Cost."}]}, {}),
            (positive, {}), ({"supported": True}, {}),
            (positive, {}), ({"supported": True}, {}),
            RuntimeError("judge unavailable"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                grade_evidence({"question": "Why?"}, [{"text": "Cost."}], ["Cost."])

    def test_joint_score_averages_rounds_that_pass_both_checks(self):
        evidence = [{"hit": value} for value in (True, True, False)]
        answers = [{"correct": value} for value in (True, False, True)]
        self.assertAlmostEqual(joint_accuracy(evidence, answers, 3), 1 / 3)
        self.assertEqual(joint_accuracy([{"hit": True}] * 3,
                                        [{"correct": True}] * 3, 3), 1)
        self.assertEqual(joint_accuracy([{"hit": False}] * 3,
                                        [{"correct": True}] * 3, 3), 0)

    def test_missing_judgment_cannot_shrink_the_denominator(self):
        for evidence, answers in [(2, 3), (3, 2), (0, 3)]:
            with self.subTest(evidence=evidence, answers=answers):
                with self.assertRaisesRegex(ValueError, "All evidence and answer"):
                    joint_accuracy([{"hit": True}] * evidence,
                                   [{"correct": True}] * answers, 3)

    def test_no_evidence_has_three_zero_outcomes_without_judge_calls(self):
        with patch("harness.llm") as model:
            result = grade_evidence({"question": "Why?"}, [], [])
        self.assertEqual(result["hit"], 0)
        self.assertEqual(len(result["votes"]), 3)
        self.assertEqual(joint_accuracy(result["votes"], [{"correct": True}] * 3, 3), 0)
        model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
