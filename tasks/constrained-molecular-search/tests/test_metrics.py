import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "environment" / "runtime"))
from metrics import TARGETS, recalls, reward, summarize, validate_ids


class MetricsTest(unittest.TestCase):
    def test_set_recall_keeps_missing_slots_and_order_is_irrelevant(self):
        truth = np.arange(10_000)
        ids = np.arange(1999, -1, -1)
        self.assertEqual(recalls(ids, truth), [.2])
        self.assertEqual(recalls([], truth), [0.0])
        self.assertEqual(recalls([0, 2], np.arange(7), (7,)), [2 / 7])

    def test_invalid_ids(self):
        for ids in ([1, 1], [-1], [10], [True], [1.0], ["1"], None, list(range(10_001))):
            with self.subTest(ids=str(ids)[:30]), self.assertRaises(ValueError):
                validate_ids(ids, 10)
        self.assertEqual(validate_ids([], 10).tolist(), [])
        self.assertEqual(validate_ids([9, 0], 10).tolist(), [9, 0])

    def test_macro_targets_not_query_counts_and_timeouts_keep_denominator(self):
        rows = [{"target": t, "recalls": [1.0]} for t in TARGETS]
        rows.append({"target": TARGETS[0], "recalls": [0.0], "status": "timeout"})
        q, by_target = summarize(rows)
        self.assertEqual(by_target[TARGETS[0]], .5)
        self.assertEqual(q, .9)

    def test_baseline_reference_and_clipping(self):
        self.assertEqual(reward(.2, 0, 1), .2)
        self.assertEqual(reward(.4, .4, .6), 0)
        self.assertAlmostEqual(reward(.5, .4, .6), .5)
        self.assertEqual(reward(.9, .4, .6), 1)
        for b, u in ((.4, .4), (.6, .4), (0, float("nan"))):
            with self.assertRaises(ValueError):
                reward(.5, b, u)


if __name__ == "__main__":
    unittest.main()
