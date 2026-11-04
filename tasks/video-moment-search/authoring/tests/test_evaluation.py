
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest
from evaluation import iou, utility, quality, validate


class Tests(unittest.TestCase):
    def test_thresholds(self):
        for x in [0.3, 0.49]:
            self.assertAlmostEqual(utility(x), 0.3 * x)
        for x, count in [(0.5, 1), (0.7, 2), (0.9, 3)]:
            self.assertAlmostEqual(utility(x), 0.7 * count / 3 + 0.3 * x)

    def test_exact(self):
        self.assertAlmostEqual(
            quality([2, 5], {"windows": [[2, 5]], "upper_bound": 1}), 1
        )

    def test_no_overlap(self):
        self.assertAlmostEqual(
            quality([0, 1], {"windows": [[2, 3]], "upper_bound": 1}), 0
        )

    def test_multiple(self):
        self.assertAlmostEqual(
            quality([8, 10], {"windows": [[0, 2], [8, 10]], "upper_bound": 1}), 1
        )

    def test_grid_ceiling(self):
        u = utility(2 / 3)
        self.assertAlmostEqual(
            quality([0, 2], {"windows": [[0, 3]], "upper_bound": u}), 1
        )

    def test_same_window(self):
        self.assertAlmostEqual(
            quality([0, 10], {"windows": [[0, 2], [8, 10]], "upper_bound": 1}), 0.06
        )

    def test_coordinates(self):
        self.assertEqual(
            validate(
                {"query_id": "q", "video_id": "v"},
                {"query_id": "q", "start": 0, "end": 2},
                {"v": {"grid": [0, 1, 2]}},
            ),
            [0, 2],
        )

    def test_invalid(self):
        for a, b in [(0, 0), (2, 1), (0.5, 2), (float("nan"), 2), (True, 2)]:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                validate(
                    {"query_id": "q", "video_id": "v"},
                    {"query_id": "q", "start": a, "end": b},
                    {"v": {"grid": [0, 1, 2]}},
                )
