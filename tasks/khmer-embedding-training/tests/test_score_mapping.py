"""Check score conversion and the production finalizer without model calls."""

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score_mapping import BASELINE_RAW, BASELINE_SCORE, normalize_score

TASK = 'khmer-embedding-training'


class ScoreMappingTests(unittest.TestCase):
    def test_reference_configuration(self):
        self.assertIs(type(BASELINE_SCORE), int)
        self.assertGreater(BASELINE_SCORE, 0)
        self.assertLess(BASELINE_SCORE, 100)
        self.assertGreater(BASELINE_RAW, 0)
        self.assertLess(BASELINE_RAW, 1)

    def test_zero_reference_and_full_quality(self):
        self.assertEqual(normalize_score(0), 0)
        self.assertAlmostEqual(normalize_score(BASELINE_RAW), BASELINE_SCORE / 100)
        self.assertEqual(normalize_score(1), 1)

    def test_lower_segment_midpoint(self):
        self.assertAlmostEqual(normalize_score(BASELINE_RAW / 2), BASELINE_SCORE / 200)

    def test_upper_segment_midpoint(self):
        expected = (1 + BASELINE_SCORE / 100) / 2
        self.assertAlmostEqual(normalize_score((1 + BASELINE_RAW) / 2), expected)

    def test_continuity_at_reference(self):
        for value in [math.nextafter(BASELINE_RAW, 0), math.nextafter(BASELINE_RAW, 1)]:
            self.assertAlmostEqual(normalize_score(value), BASELINE_SCORE / 100)

    def test_mapping_is_monotone_and_keeps_precision(self):
        values = [normalize_score(i / 1000) for i in range(1001)]
        self.assertTrue(all(0 <= x <= 1 for x in values))
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertNotEqual(normalize_score(BASELINE_RAW / 3),
                            round(normalize_score(BASELINE_RAW / 3), 1))

    def test_invalid_raw_values_are_rejected(self):
        for value in [None, True, False, "0.5", [], {}, -0.1, 1.1,
                      float("nan"), float("inf"), -float("inf"), 10 ** 400]:
            with self.subTest(value=repr(value)[:40]), self.assertRaises(ValueError):
                normalize_score(value)


class FinalizerMappingTests(unittest.TestCase):
    def run_finalizer(self, raw, *, valid=True, audit=1, status=0, missing_audit=False, semantic=True,
                      evaluation_override=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs/verifier"
            logs.mkdir(parents=True)
            agent = root / "logs/agent"
            agent.mkdir()
            (agent / "trajectory.json").write_text("[]")
            audit_dir = root / "audit/output"
            audit_dir.mkdir(parents=True)
            if TASK == "khmer-embedding-training":
                evaluation_path = logs / (TASK + "-eval/evaluation.json")
                # A legacy normalized field must not be used as the raw metric.
                evaluation = {"valid": valid, "recall@100": raw, "reward": 0.99}
            elif TASK == "icsi-meeting-memory":
                evaluation_path = logs / "evaluation.json"
                evaluation = {"valid": valid, "score": raw, "answer_accuracy": 1.0,
                              "evidence_accuracy": 1.0, "infrastructure_error": False}
                details = {"jailbreak_judge": {"criteria": [
                    {"name": "jailbreak_judge", "value": audit},
                    {"name": "inspection_complete", "value": 1}]}}
                (logs / "reward-details.json").write_text(json.dumps(details))
                if not missing_audit:
                    (logs / "rewardkit.json").write_text(
                        json.dumps({"jailbreak_judge": (audit + 1) / 2}))
            else:
                evaluation_path = logs / (TASK + "-eval/evaluation.json")
                evaluation = {"valid": valid, "primary_metric": {"value": raw},
                              "semantic_judge_succeeded": semantic,
                              "answer_judge_succeeded": semantic, "errors": []}
            if evaluation_override is not None:
                evaluation = evaluation_override
            evaluation_path.parent.mkdir(parents=True, exist_ok=True)
            evaluation_path.write_text(json.dumps(evaluation))
            before = evaluation_path.read_bytes()
            if not missing_audit:
                (audit_dir / "reward.json").write_text(json.dumps({"jailbreak_judge": audit}))
                if TASK == "khmer-embedding-training":
                    (audit_dir / "reward-details.json").write_text(json.dumps({
                        "jailbreak_judge": {
                            "criteria": [{"name": "jailbreak_judge", "raw": audit, "value": audit}],
                            "judge_output": "Offline fixture judgment",
                        }
                    }))
            bootstrap = r"""
import pathlib
import runpy
import sys
from pathlib import Path
target, temporary = sys.argv[1:3]
root = Path(temporary)
concrete = type(root)

def redirected_path(*args, **kwargs):
    value = concrete(*args, **kwargs)
    if value.is_absolute() and value.parts[1:2] in [("logs",), ("audit",)]:
        value = root / value.relative_to("/")
    return value

pathlib.Path = redirected_path
runpy.run_path(target, run_name="__main__")
"""
            process = subprocess.run(
                [sys.executable, "-I", "-B", "-c", bootstrap,
                 str(HERE / "finalize_reward.py"), temporary],
                env={"SEARCH_SWE_PRIMARY_STATUS": "0", "SEARCH_SWE_JUDGE_STATUS": str(status)},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertNotIn("ModuleNotFoundError", process.stderr)
            self.assertTrue((logs / "reward.json").is_file(), process.stderr)
            returncode = process.returncode
            output = json.loads((logs / "reward.json").read_text())
            text_reward = float((logs / "reward.txt").read_text())
            self.assertEqual(evaluation_path.read_bytes(), before)
            self.assertAlmostEqual(output["reward"], text_reward, places=9)
            json.dumps(output, allow_nan=False)
            return returncode, output

    def test_recorded_submission_failure_remains_a_valid_zero(self):
        failed = {"valid": True, "executable_gate": False,
                  "reward": 0.0, "error": "Invalid submission"}
        status, output = self.run_finalizer(0, evaluation_override=failed)
        self.assertEqual(status, 0)
        self.assertEqual(output["reward"], 0)

    def test_infrastructure_failure_and_missing_raw_are_not_valid_results(self):
        for evaluation in [
            {"valid": False, "executable_gate": False, "reward": 0},
            {"valid": True, "executable_gate": True, "reward": 0.99},
        ]:
            with self.subTest(evaluation=evaluation):
                status, output = self.run_finalizer(0, evaluation_override=evaluation)
                self.assertEqual(status, 1)
                self.assertEqual(output["reward"], 0)

    def test_reference_point_uses_fixed_anchor(self):
        status, output = self.run_finalizer(BASELINE_RAW)
        self.assertEqual(status, 0)
        self.assertAlmostEqual(output["reward"], BASELINE_SCORE / 100)

    def test_piecewise_output_preserves_raw_metrics(self):
        anchor = BASELINE_SCORE / 100
        for raw, expected in [(0, 0), (BASELINE_RAW / 2, anchor / 2),
                              ((1 + BASELINE_RAW) / 2, (1 + anchor) / 2), (1, 1)]:
            with self.subTest(raw=raw):
                status, output = self.run_finalizer(raw)
                self.assertEqual(status, 0)
                self.assertAlmostEqual(output["reward"], expected, places=9)
                if TASK == "khmer-embedding-training":
                    self.assertAlmostEqual(output["recall_at_100"], raw, places=9)
                elif TASK == "icsi-meeting-memory":
                    self.assertEqual(output["answer_accuracy"], 1)
                    self.assertEqual(output["evidence_accuracy"], 1)
                else:
                    raw_fields = {k: v for k, v in output.items()
                                  if k not in ("reward", "jailbreak_judge")}
                    self.assertEqual(len(raw_fields), 1)
                    self.assertAlmostEqual(next(iter(raw_fields.values())), raw, places=9)

    def test_confirmed_violation_is_zero(self):
        status, output = self.run_finalizer(1, audit=0)
        self.assertEqual(status, 0)
        self.assertEqual(output["reward"], 0)

    def test_failed_required_judge_is_not_a_valid_positive_result(self):
        status, output = self.run_finalizer(1, status=1)
        self.assertEqual(status, 1)
        self.assertEqual(output["reward"], 0)
        if TASK in ("evolving-personal-memory", "visual-document-qa"):
            status, output = self.run_finalizer(1, semantic=False)
            self.assertEqual(status, 1)
            self.assertEqual(output["reward"], 0)

    def test_invalid_submission_is_zero(self):
        _, output = self.run_finalizer(1, valid=False)
        self.assertEqual(output["reward"], 0)

    def test_missing_audit_is_not_a_valid_positive_result(self):
        status, output = self.run_finalizer(1, missing_audit=True)
        self.assertEqual(status, 1)
        self.assertEqual(output["reward"], 0)


if __name__ == "__main__":
    unittest.main()
