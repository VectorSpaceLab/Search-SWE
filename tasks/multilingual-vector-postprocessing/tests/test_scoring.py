"""CPU-only checks of the real grader's score and the final integrity gate."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from finalize import combine


ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScoringTests(unittest.TestCase):
    def grade_quality(self, quality):
        evaluator = types.ModuleType("evaluate")
        evaluator.evaluate = Mock(return_value={"Q": quality, "total_queries": 13002})
        isolation = types.ModuleType("isolation")
        isolation.cleanup = Mock()
        metrics = load_module("postprocessing_metrics", ROOT / "runtime" / "metrics.py")
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(sys.modules, {"evaluate": evaluator, "isolation": isolation, "metrics": metrics}), \
                patch.object(sys, "path", list(sys.path)):
            grader = load_module("postprocessing_grader", ROOT / "grade.py")
            grader.OUT = Path(directory)
            status = grader.main()
            report = json.loads((grader.OUT / "report.json").read_text())
        return status, report

    def test_baseline_and_lower_quality_score_zero(self):
        for quality in (0.0, 0.9, 0.9127469497437668):
            with self.subTest(quality=quality):
                status, report = self.grade_quality(quality)
                self.assertEqual(status, 0)
                self.assertTrue(report["valid"])
                self.assertEqual(report["score_100"], 0.0)

    def test_linear_scores_reach_full_credit_only_at_one(self):
        for quality, expected in (
            (0.9353486724891793, 25.90364769946581),
            (0.95, 42.69541310800411),
            (0.9563734748718834, 50.0),
            (1.0, 100.0),
        ):
            with self.subTest(quality=quality):
                status, report = self.grade_quality(quality)
                self.assertEqual(status, 0)
                self.assertEqual(report["baseline"], 0.9127469497437668)
                self.assertEqual(report["reference"], 1.0)
                self.assertAlmostEqual(report["score_100"], expected)
                self.assertAlmostEqual(report["reward"], expected / 100)

    def test_invalid_quality_fails_closed(self):
        for quality in (float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(quality=quality):
                status, report = self.grade_quality(quality)
                self.assertEqual(status, 1)
                self.assertFalse(report["valid"])
                self.assertEqual(report["reward"], 0.0)

    def test_new_score_still_requires_successful_integrity_review(self):
        _, report = self.grade_quality(0.95)
        for decision, status, expected in ((1, "0", 0.4269541310800411), (0, "0", 0.0), (1, "1", 0.0)):
            with self.subTest(decision=decision, status=status):
                details = {"jailbreak_judge": {
                    "criteria": [{"name": "integrity", "raw": decision}],
                    "judge_output": "Offline test decision",
                }}
                result, _ = combine(report, {"jailbreak_judge": decision}, status, True, details)
                self.assertAlmostEqual(result["reward"], expected)


if __name__ == "__main__":
    unittest.main()
