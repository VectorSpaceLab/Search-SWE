import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("task2_4_verify", Path(__file__).with_name("verify.py"))
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class RewardTests(unittest.TestCase):
    def test_harbor_receives_only_gold_recall(self):
        cases = [
            ({"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": 0.7}}, 0.7),
            ({"valid": False, "primary_metric": {"name": "GoldRecall@5", "value": 1}}, 0.0),
            ({"valid": True, "primary_metric": {"name": "other_metric", "value": 1}}, 0.0),
            ({"valid": True, "primary_metric": {"name": "GoldRecall@5", "value": float("nan")}}, 0.0),
            ({}, 0.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(VERIFY, "REWARD_DIR", root):
                for report, expected in cases:
                    with self.subTest(report=report):
                        self.assertEqual(VERIFY.write_reward(report), expected)
                        self.assertEqual(float((root / "reward.txt").read_text()), expected)
                        self.assertEqual(json.loads((root / "reward.json").read_text()), {"gold_recall_at_5": expected})


if __name__ == "__main__":
    unittest.main()
