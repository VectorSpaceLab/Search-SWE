
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest
from evaluation import quality, validate, aggregate


class Cases(unittest.TestCase):
    def test_rank_one(self):
        self.assertEqual(quality(["a"], {"a": 1}), 1)

    def test_rank_two(self):
        self.assertEqual(quality(["x", "a"], {"a": 1}), 0.75)

    def test_rank_three(self):
        self.assertAlmostEqual(quality(["x", "y", "a"], {"a": 1}), 2 / 3)

    def test_rank_four(self):
        self.assertEqual(quality(["x", "y", "z", "a"], {"a": 1}), 0)

    def test_rank_ten(self):
        self.assertEqual(quality(list("123456789") + ["a"], {"a": 1}), 0)

    def test_miss(self):
        self.assertEqual(quality(["b"], {"a": 1}), 0)

    def test_input_validation(self):
        q = {"query_id": "q"}
        pages = {"a": {}}
        self.assertEqual(
            validate(
                q,
                {"query_id": "q", "results": [{"image_id": "a", "score": 0.5}]},
                pages,
            ),
            ["a"],
        )
        for result in [
            [{"image_id": "a", "score": True}],
            [{"image_id": "x", "score": 0.5}],
            [{"image_id": "a", "score": 1}, {"image_id": "a", "score": 0.5}],
        ]:
            with self.assertRaises(ValueError):
                validate(q, {"query_id": "q", "results": result}, pages)

    def test_level_macro(self):
        self.assertEqual(
            aggregate(
                [
                    {"domain": "level1", "value": 1},
                    {"domain": "level1", "value": 0},
                    {"domain": "level2", "value": 1},
                ]
            )[0],
            0.75,
        )


if __name__ == "__main__":
    unittest.main()
