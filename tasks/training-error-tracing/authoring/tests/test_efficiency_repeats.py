"""Repeated latency aggregation keeps equal query/group weighting."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest
from efficiency_metrics import latency_metric, quality_gate


class EfficiencyRepeatTests(unittest.TestCase):
    def test_query_medians_then_equal_group_weights(self):
        passes = [[{"id": "a", "group_id": "one", "elapsed_sec": value},
                   {"id": "b", "group_id": "two", "elapsed_sec": 2},
                   {"id": "c", "group_id": "two", "elapsed_sec": 6}]
                  for value in [1, 2, 3, 7, 30]]
        self.assertEqual(latency_metric(passes), 3.5)  # mean(median(a)=3, mean(b=2, c=6))

    def test_requires_exactly_five_passes(self):
        valid = [{"id": "a", "group_id": "one", "elapsed_sec": 1}]
        for count in (0, 1, 3, 4, 6):
            with self.subTest(count=count), self.assertRaises(ValueError):
                latency_metric([valid] * count)

    def test_missing_or_invalid_repetition_cannot_be_dropped(self):
        valid = [{"id": "a", "group_id": "one", "elapsed_sec": 1}]
        for bad in [[], [dict(valid[0], elapsed_sec=float("nan"))], [dict(valid[0], id="wrong")]]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                latency_metric([valid, valid, valid, valid, bad])

    def test_quality_must_still_pass_every_repetition(self):
        good = {"Q": 1, "groups": {"one": {"p10": 1}}}
        bad = {"Q": .97, "groups": {"one": {"p10": .97}}}
        self.assertFalse(quality_gate([good, good, good, good, bad]))


if __name__ == "__main__":
    unittest.main()
